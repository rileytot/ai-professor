"""The professor (teaching) context.

Subordinate to the curriculum (invariant #1). It may *propose* advancement via ``nextTopic``,
which triggers a fresh judger; it can never *grant* it. Note that ``build_professor_registry``
takes **no ledger handle** -- the teaching context is structurally never given the ability to
write progression state. Teaching/hint generation (LLM-backed) is wired in Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_professor.tools.registry import Tool, ToolRegistry


@dataclass(frozen=True, slots=True)
class NextTopicProposal:
    """A request to advance, to be adjudicated by a separate judger. Not a grant."""

    from_node: str


def propose_next_topic(from_node: str) -> NextTopicProposal:
    """The professor's only progression action: propose advancement from the current node."""
    return NextTopicProposal(from_node=from_node)


def build_professor_registry() -> ToolRegistry:
    """Tools available to the teaching context. Deliberately omits ``confirmMilestone``.

    (serve-variant / submit-answer / get-hint are added in later phases; none grant progression.)
    """
    return ToolRegistry(
        [
            Tool(
                name="nextTopic",
                handler=propose_next_topic,
                description="Propose advancement from the current node; triggers a fresh judger.",
            ),
        ]
    )
