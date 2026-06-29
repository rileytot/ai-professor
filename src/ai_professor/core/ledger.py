"""The milestone ledger and its capability token (invariant #1).

Authority over progression lives here, not in the teaching model. The ledger is append-only
(it writes through the append-only event log) and its sole mutating method, ``confirm``, demands
a ``VerifiedProof`` -- an unforgeable token that can only be minted via ``mint_proof`` using a
module-private guard. The judger calls ``mint_proof`` *after* its checks pass; the professor
context is never given ``mint_proof`` or a ledger handle (see ``contexts.professor``).

So a ``MilestoneConfirmed`` event can never reach the log without going through verification.
Python cannot make this cryptographically airtight (a determined caller could reach into a
``_private`` name), so the guarantee is structural + convention + the test wall -- which is the
accepted posture for the Python core (see ``CLAUDE.md`` / ``PLAN.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from ai_professor.core.errors import ProofForgeryError
from ai_professor.core.events import MilestoneConfirmed, RecordedEvent
from ai_professor.core.stores import EventLog

# Module-private capability sentinel. Only ``mint_proof`` (below) holds it, so only this module
# can construct a valid VerifiedProof. Never export this.
_MINT: Final[object] = object()


@dataclass(frozen=True)
class VerifiedProof:
    """Unforgeable receipt that the judger verified a milestone was satisfied.

    Construct ONLY via ``mint_proof``. Direct construction has no guard and is rejected.
    ``evidence`` records the proof material (e.g. the ids of the correct submissions) for audit.
    """

    milestone_id: str
    node_id: str
    proof_id: str
    evidence: tuple[str, ...]
    _guard: object = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self._guard is not _MINT:
            raise ProofForgeryError(
                "VerifiedProof must be created via mint_proof(), not constructed directly"
            )


def mint_proof(
    *, milestone_id: str, node_id: str, proof_id: str, evidence: tuple[str, ...]
) -> VerifiedProof:
    """Mint a proof. Called by the judger only after its (v1: CAS-deterministic) checks pass."""
    return VerifiedProof(
        milestone_id=milestone_id,
        node_id=node_id,
        proof_id=proof_id,
        evidence=evidence,
        _guard=_MINT,
    )


class MilestoneLedger:
    """Append-only milestone ledger. The sole grant path; writes via the append-only event log."""

    def __init__(self, events: EventLog) -> None:
        self._events = events

    def confirm(self, proof: VerifiedProof, *, stream: str = "default") -> RecordedEvent:
        """Record a milestone as satisfied. Requires a genuinely-minted ``VerifiedProof``."""
        if not isinstance(proof, VerifiedProof):  # defends against duck-typed forgeries
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
