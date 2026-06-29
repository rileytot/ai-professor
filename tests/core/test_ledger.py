"""Tests for the milestone ledger and its unforgeable capability token (invariant #1)."""

from __future__ import annotations

import types

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
