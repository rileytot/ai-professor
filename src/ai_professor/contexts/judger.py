"""The judger (gating) context.

Runs in a lean, isolated context with an adversarial objective (invariant #2): it sees only the
learner's current-topic work plus the relevant milestones -- never the teaching transcript. In
v1 the judger is **deterministic** (CAS + policy), so it needs no LLM; the LLM-judger machinery
is the post-v1 extension point. It is the sole holder of ``confirmMilestone`` -- the only path
that can grant progression -- and to use it, it must first mint a ``VerifiedProof``.

The deterministic verification policy (run the CAS checks, then mint on success) is wired in
Phase 3, once the grading rail exists.
"""

from __future__ import annotations

from ai_professor.core.events import RecordedEvent
from ai_professor.core.ledger import MilestoneLedger, VerifiedProof
from ai_professor.tools.registry import Tool, ToolRegistry


def build_judger_registry(ledger: MilestoneLedger) -> ToolRegistry:
    """Tools available to the judging context. Holds ``confirmMilestone`` -- the sole grant path.

    Requires a ledger handle (contrast ``build_professor_registry``, which takes none): authority
    to write progression is given only to the judger.
    """

    def confirm_milestone(proof: VerifiedProof) -> RecordedEvent:
        return ledger.confirm(proof)

    return ToolRegistry(
        [
            Tool(
                name="confirmMilestone",
                handler=confirm_milestone,
                description="Grant a milestone, given a VerifiedProof minted after verification.",
            ),
        ]
    )
