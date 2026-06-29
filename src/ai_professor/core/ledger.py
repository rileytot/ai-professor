"""The milestone ledger and its capability token (invariant #1).

Authority over progression lives here, not in the teaching model. The ledger is append-only
(it writes through the append-only event log) and its sole mutating method, ``confirm``, demands
a ``VerifiedProof`` -- a token that can only be produced by ``mint_proof``. The judger calls
``mint_proof`` *after* its checks pass; the professor context is never given ``mint_proof`` or a
ledger handle (see ``contexts.professor``). So a ``MilestoneConfirmed`` event can never reach the
log without going through verification.

Forgery defense is two-layered, because a single guard is not enough (an earlier field-based guard
was forgeable via ``dataclasses.replace``):
1. ``VerifiedProof`` is not a dataclass and its constructor requires a module-private guard, so
   direct construction and ``dataclasses.replace`` both fail.
2. Every genuinely-minted proof is recorded by identity in a module-private registry that
   ``confirm`` checks. A copy, pickle round-trip, ``object.__new__`` instance, or subclass that
   bypasses the constructor is simply not in the registry, so ``confirm`` rejects it.

Python cannot make this cryptographically airtight (a determined caller could still reach a
``_private`` name), so the residual guarantee is structural + convention + the test wall -- the
accepted posture for the Python core (see ``CLAUDE.md`` / ``PLAN.md``).
"""

from __future__ import annotations

import weakref
from typing import Final

from ai_professor.core.errors import ProofForgeryError
from ai_professor.core.events import MilestoneConfirmed, RecordedEvent
from ai_professor.core.stores import EventLog

# Module-private capability sentinel. Only ``mint_proof`` holds it. Never export this.
_MINT: Final[object] = object()


class VerifiedProof:
    """Unforgeable receipt that the judger verified a milestone was satisfied. Immutable.

    Create ONLY via ``mint_proof``. ``evidence`` records the proof material (e.g. the ids of the
    correct submissions) for audit.
    """

    milestone_id: str
    node_id: str
    proof_id: str
    evidence: tuple[str, ...]
    __slots__ = ("__weakref__", "evidence", "milestone_id", "node_id", "proof_id")

    def __init__(
        self,
        *,
        milestone_id: str,
        node_id: str,
        proof_id: str,
        evidence: tuple[str, ...],
        _mint_guard: object = None,
    ) -> None:
        if _mint_guard is not _MINT:
            raise ProofForgeryError(
                "VerifiedProof must be created via mint_proof(), not constructed directly"
            )
        object.__setattr__(self, "milestone_id", milestone_id)
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "proof_id", proof_id)
        object.__setattr__(self, "evidence", evidence)

    def __setattr__(self, name: str, value: object) -> None:  # immutable after construction
        raise AttributeError("VerifiedProof is immutable")

    def __repr__(self) -> str:
        return f"VerifiedProof(milestone_id={self.milestone_id!r}, node_id={self.node_id!r})"


# Identity registry of genuinely-minted proofs (weak so confirmed proofs can be collected).
_MINTED: Final[weakref.WeakSet[VerifiedProof]] = weakref.WeakSet()


def mint_proof(
    *, milestone_id: str, node_id: str, proof_id: str, evidence: tuple[str, ...]
) -> VerifiedProof:
    """Mint a proof. Called by the judger only after its (v1: CAS-deterministic) checks pass."""
    proof = VerifiedProof(
        milestone_id=milestone_id,
        node_id=node_id,
        proof_id=proof_id,
        evidence=evidence,
        _mint_guard=_MINT,
    )
    _MINTED.add(proof)
    return proof


def is_genuine(proof: object) -> bool:
    """True only for a proof actually produced by ``mint_proof`` (checked by identity)."""
    return isinstance(proof, VerifiedProof) and proof in _MINTED


class MilestoneLedger:
    """Append-only milestone ledger. The sole grant path; writes via the append-only event log."""

    def __init__(self, events: EventLog) -> None:
        self._events = events

    def confirm(self, proof: VerifiedProof, *, stream: str = "default") -> RecordedEvent:
        """Record a milestone as satisfied. Requires a genuinely-minted ``VerifiedProof``."""
        if not is_genuine(proof):
            raise ProofForgeryError()
        return self._events.append(
            MilestoneConfirmed(
                milestone_id=proof.milestone_id,
                node_id=proof.node_id,
                proof_id=proof.proof_id,
            ),
            stream=stream,
        )

    def confirmed(self, *, stream: str | None = None) -> frozenset[str]:
        """The set of milestone ids confirmed so far (read from the append-only log)."""
        return frozenset(
            rec.event.milestone_id
            for rec in self._events.read(stream=stream)
            if isinstance(rec.event, MilestoneConfirmed)
        )
