"""Domain events and their (de)serialization.

Events are immutable facts ("this happened"). The append-only log (``core.stores.EventLog``)
is the single source of truth; the knowledge state is a *derived projection* folded from these
events (``core.projection``). Keeping events as small frozen dataclasses with a tiny registry
keeps the integrity core dependency-free (stdlib only) and easy to port later.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from ai_professor.core.errors import UnknownEventType


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Immutable base for domain events. Concrete subclasses are registered via ``@event``."""


_REGISTRY: dict[str, Callable[..., DomainEvent]] = {}


def event(cls: type[DomainEvent]) -> type[DomainEvent]:
    """Class decorator: register an event type under its class name for (de)serialization."""
    _REGISTRY[cls.__name__] = cls
    return cls


def serialize(ev: DomainEvent) -> tuple[str, dict[str, Any]]:
    """Return ``(type_name, payload)`` where payload is a JSON-serializable dict of the fields."""
    return type(ev).__name__, asdict(ev)


def deserialize(type_name: str, payload: Mapping[str, Any]) -> DomainEvent:
    """Reconstruct a domain event from its stored ``type_name`` + ``payload``."""
    ctor = _REGISTRY.get(type_name)
    if ctor is None:
        raise UnknownEventType(type_name)
    return ctor(**payload)


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """An event as it lives in the log: the domain event plus its assigned position + timestamp."""

    seq: int
    stream: str
    ts: str  # ISO-8601 UTC, assigned at append time
    event: DomainEvent


# --- v1 domain events -------------------------------------------------------------------------
# Audit-trail granularity for the single-chapter slice. More will be added as phases land
# (ReviewPerformed, CheckpointTaken, ...). Each must round-trip through JSON (flat scalar fields).


@event
@dataclass(frozen=True, slots=True)
class TopicStarted(DomainEvent):
    """The professor began teaching a curriculum node."""

    node_id: str


@event
@dataclass(frozen=True, slots=True)
class ProblemServed(DomainEvent):
    """A numeric-template variant was served to the learner (audit only; no state change)."""

    node_id: str
    item_id: str
    variant_seed: int


@event
@dataclass(frozen=True, slots=True)
class AnswerSubmitted(DomainEvent):
    """The learner submitted an answer to a served variant; ``correct`` is the CAS verdict."""

    node_id: str
    item_id: str
    variant_seed: int
    correct: bool


@event
@dataclass(frozen=True, slots=True)
class MilestoneConfirmed(DomainEvent):
    """The judger confirmed a milestone. The sole ledger-mutating event (invariant #1).

    ``proof_id`` references the recorded proof (e.g. the run of correct submissions) for audit.
    """

    milestone_id: str
    node_id: str
    proof_id: str


@event
@dataclass(frozen=True, slots=True)
class TopicAdvanced(DomainEvent):
    """Progression from one node to the next."""

    from_node: str
    to_node: str
