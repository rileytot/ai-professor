"""Knowledge projection: the derived read model (store 2).

The knowledge state is *not* stored directly — it is folded from the append-only event log on
demand. This gives replay and time-travel (``as_of``) for free, and a clean split between "what
happened" (the log) and "current mastery" (this projection). Per DESIGN.md §7, relevance is
selected by graph adjacency elsewhere; this module just computes state from events.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Protocol

from ai_professor.core.events import (
    AnswerSubmitted,
    MilestoneConfirmed,
    RecordedEvent,
    TopicAdvanced,
    TopicStarted,
)


class ReadableLog(Protocol):
    """Structural type for the read side of the event log (decouples projection from stores)."""

    def read(
        self, *, stream: str | None = ..., up_to_seq: int | None = ...
    ) -> list[RecordedEvent]: ...


@dataclass(frozen=True, slots=True)
class NodeState:
    """Per-node mastery snapshot. ``last_seq`` aids failure localization (DESIGN.md §7)."""

    node_id: str
    correct_submissions: int = 0
    confirmed_milestones: frozenset[str] = frozenset()
    last_seq: int = 0


@dataclass(frozen=True, slots=True)
class KnowledgeState:
    """Folded learner state. Immutable: ``apply`` returns a new instance per event."""

    nodes: Mapping[str, NodeState] = field(default_factory=dict)
    confirmed_milestones: frozenset[str] = frozenset()
    current_node: str | None = None
    version: int = 0  # seq of the last applied event

    def node(self, node_id: str) -> NodeState:
        """Return the node's state, or a fresh empty one if it has no events yet."""
        return self.nodes.get(node_id, NodeState(node_id=node_id))


def apply(state: KnowledgeState, rec: RecordedEvent) -> KnowledgeState:
    """Pure fold step: fold one recorded event into the state, returning a new state."""
    ev = rec.event
    nodes = dict(state.nodes)
    confirmed = state.confirmed_milestones
    current = state.current_node

    if isinstance(ev, TopicStarted):
        nodes[ev.node_id] = replace(state.node(ev.node_id), last_seq=rec.seq)
        current = ev.node_id
    elif isinstance(ev, AnswerSubmitted):
        ns = state.node(ev.node_id)
        nodes[ev.node_id] = replace(
            ns,
            correct_submissions=ns.correct_submissions + (1 if ev.correct else 0),
            last_seq=rec.seq,
        )
    elif isinstance(ev, MilestoneConfirmed):
        ns = state.node(ev.node_id)
        nodes[ev.node_id] = replace(
            ns,
            confirmed_milestones=ns.confirmed_milestones | {ev.milestone_id},
            last_seq=rec.seq,
        )
        confirmed = confirmed | {ev.milestone_id}
    elif isinstance(ev, TopicAdvanced):
        current = ev.to_node
    # ProblemServed and any unhandled event: audit-only, no state change.

    return KnowledgeState(
        nodes=nodes,
        confirmed_milestones=confirmed,
        current_node=current,
        version=rec.seq,
    )


def fold(events: Iterable[RecordedEvent], initial: KnowledgeState | None = None) -> KnowledgeState:
    """Fold a sequence of events into a single ``KnowledgeState``."""
    state = initial if initial is not None else KnowledgeState()
    for rec in events:
        state = apply(state, rec)
    return state


class KnowledgeProjection:
    """Derived read model over an event log: recomputed on demand (the log is authoritative)."""

    def __init__(self, log: ReadableLog) -> None:
        self._log = log

    def current(self, *, stream: str | None = None) -> KnowledgeState:
        """State after applying every event (optionally filtered to one stream)."""
        return fold(self._log.read(stream=stream))

    def as_of(self, seq: int, *, stream: str | None = None) -> KnowledgeState:
        """Time-travel: state after applying events up to and including ``seq``."""
        return fold(self._log.read(stream=stream, up_to_seq=seq))
