"""Tests for the milestone ledger and its unforgeable capability token (invariant #1)."""

from __future__ import annotations

import copy
import dataclasses
import pickle
import types
from collections.abc import Callable

import pytest

from ai_professor.core.errors import ProofForgeryError
from ai_professor.core.ledger import MilestoneLedger, VerifiedProof, mint_proof
from ai_professor.core.stores import Stores


def test_verified_proof_cannot_be_constructed_directly() -> None:
    with pytest.raises(ProofForgeryError):
        VerifiedProof(milestone_id="m1", node_id="7.1", proof_id="p1", evidence=())


def test_mint_proof_produces_a_valid_proof() -> None:
    proof = mint_proof(milestone_id="m1", node_id="7.1", proof_id="p1", evidence=("s1", "s2"))
    assert isinstance(proof, VerifiedProof)
    assert proof.milestone_id == "m1"
    assert proof.evidence == ("s1", "s2")


def test_confirm_appends_milestone_and_is_visible(stores: Stores) -> None:
    ledger = MilestoneLedger(stores.events)
    proof = mint_proof(milestone_id="m1", node_id="7.1", proof_id="p1", evidence=("s1",))
    rec = ledger.confirm(proof)
    assert rec.seq == 1
    assert ledger.confirmed() == frozenset({"m1"})
    # The confirmation flows through the append-only log into the derived projection.
    assert "m1" in stores.projection.current().confirmed_milestones


def test_confirm_rejects_forged_proof(stores: Stores) -> None:
    ledger = MilestoneLedger(stores.events)
    # A look-alike object with the right attributes is still not a minted VerifiedProof.
    fake = types.SimpleNamespace(milestone_id="m1", node_id="7.1", proof_id="p1", evidence=())
    with pytest.raises(ProofForgeryError):
        ledger.confirm(fake)  # type: ignore[arg-type]
    assert ledger.confirmed() == frozenset()


def test_confirm_writes_through_append_only_log(stores: Stores) -> None:
    ledger = MilestoneLedger(stores.events)
    ledger.confirm(mint_proof(milestone_id="m1", node_id="7.1", proof_id="p1", evidence=()))
    # The ledger has no path to rewrite history: the underlying log rejects mutation.
    import sqlite3

    with pytest.raises(sqlite3.Error, match="append-only"):
        stores.conn.execute("DELETE FROM events")


def _assert_cannot_forge(ledger: MilestoneLedger, make: Callable[[], object]) -> None:
    """A forgery either fails to construct or is rejected by confirm -- never grants."""
    try:
        forged = make()
    except (AttributeError, TypeError, ProofForgeryError, pickle.PickleError):
        return  # could not even be constructed -- blocked at the source
    with pytest.raises(ProofForgeryError):
        ledger.confirm(forged)  # type: ignore[arg-type]


def test_replace_cannot_forge_a_proof() -> None:
    # The earlier field-guard was forgeable via dataclasses.replace; VerifiedProof is now not a
    # dataclass, so replace() refuses it outright.
    real = mint_proof(milestone_id="m1", node_id="7.1", proof_id="p1", evidence=("s",))
    with pytest.raises(TypeError):
        dataclasses.replace(real, milestone_id="forged")  # type: ignore[type-var]


def test_copy_pickle_new_subclass_forgeries_are_rejected(stores: Stores) -> None:
    ledger = MilestoneLedger(stores.events)
    real = mint_proof(milestone_id="m1", node_id="7.1", proof_id="p1", evidence=("s",))

    class _Sub(VerifiedProof):
        def __init__(self) -> None:  # bypass the guarded constructor
            pass

    _assert_cannot_forge(ledger, lambda: copy.copy(real))
    _assert_cannot_forge(ledger, lambda: copy.deepcopy(real))
    _assert_cannot_forge(ledger, lambda: pickle.loads(pickle.dumps(real)))
    _assert_cannot_forge(ledger, lambda: object.__new__(VerifiedProof))
    _assert_cannot_forge(ledger, _Sub)

    assert ledger.confirmed() == frozenset()  # nothing leaked through
    ledger.confirm(real)  # the genuine proof still works
    assert ledger.confirmed() == frozenset({"m1"})


def test_verified_proof_is_immutable() -> None:
    real = mint_proof(milestone_id="m1", node_id="7.1", proof_id="p1", evidence=("s",))
    with pytest.raises(AttributeError):
        real.milestone_id = "changed"  # type: ignore[misc]
