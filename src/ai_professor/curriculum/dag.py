"""The curriculum DAG model (structure + locators only).

Per invariant #7, the shareable curriculum holds **no copyrighted content** -- only structure
(nodes, prerequisite edges, milestones) and *locators* into a source. Learning-objective and
problem text live in the local, git-ignored ``content/`` store and are rehydrated at runtime. Node
titles and milestone summaries are our own wording, not copied prose.

This model is what ``core.CurriculumStore`` persists (immutable per version), via ``to_dict`` /
``from_dict``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LearningObjectiveRef:
    """A reference to one section learning objective (the completeness unit). Text stays local."""

    id: str  # stable slug, e.g. "7.1-lo-1"
    section: str  # e.g. "7.1"
    locator: str  # e.g. "OpenStax University Physics Vol. 1 §7.1, learning objective 1"


@dataclass(frozen=True, slots=True)
class ItemRef:
    """A reference to one sourced assessment item. Problem text stays local."""

    id: str  # e.g. "7.1-p7.4"
    locator: str  # e.g. "OpenStax University Physics Vol. 1 §7.1, Problem 7.4"
    cas_verifiable: bool  # declared here; Phase 2 attaches the numeric template and verifies it


@dataclass(frozen=True, slots=True)
class Milestone:
    """A gating criterion for a node: the objectives it covers and the items that demonstrate it."""

    id: str
    node_id: str
    summary: str  # our own short description of the criterion (not copied text)
    objective_ids: tuple[str, ...]
    item_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Node:
    """A gateable topic: a cluster of one or more sections' learning objectives."""

    id: str
    title: str  # our own title, e.g. "Work"
    sections: tuple[str, ...]
    milestone_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Provenance:
    """Which sources fed the DAG and whether a human has reviewed it (DESIGN.md §4.3)."""

    sources: tuple[str, ...]
    human_reviewed: bool
    notes: str = ""


@dataclass(frozen=True, slots=True)
class CurriculumDAG:
    """A versioned, source-grounded curriculum DAG. Immutable once published."""

    version: str
    title: str
    nodes: tuple[Node, ...]
    edges: tuple[tuple[str, str], ...]  # (prerequisite_node_id, dependent_node_id)
    milestones: tuple[Milestone, ...]
    objectives: tuple[LearningObjectiveRef, ...]
    items: tuple[ItemRef, ...]
    entry_node_ids: tuple[str, ...]
    terminal_node_ids: tuple[str, ...]
    provenance: Provenance = field(
        default_factory=lambda: Provenance(sources=(), human_reviewed=False)
    )

    # --- convenience accessors (used by the QA checks) ---
    @property
    def node_ids(self) -> frozenset[str]:
        return frozenset(n.id for n in self.nodes)

    @property
    def milestone_ids(self) -> frozenset[str]:
        return frozenset(m.id for m in self.milestones)

    @property
    def objective_ids(self) -> frozenset[str]:
        return frozenset(o.id for o in self.objectives)

    @property
    def item_ids(self) -> frozenset[str]:
        return frozenset(i.id for i in self.items)

    def item(self, item_id: str) -> ItemRef | None:
        return next((i for i in self.items if i.id == item_id), None)

    # --- (de)serialization for CurriculumStore (JSON) ---
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "title": self.title,
            "nodes": [
                {
                    "id": n.id,
                    "title": n.title,
                    "sections": list(n.sections),
                    "milestone_ids": list(n.milestone_ids),
                }
                for n in self.nodes
            ],
            "edges": [[src, dst] for src, dst in self.edges],
            "milestones": [
                {
                    "id": m.id,
                    "node_id": m.node_id,
                    "summary": m.summary,
                    "objective_ids": list(m.objective_ids),
                    "item_ids": list(m.item_ids),
                }
                for m in self.milestones
            ],
            "objectives": [
                {"id": o.id, "section": o.section, "locator": o.locator} for o in self.objectives
            ],
            "items": [
                {"id": i.id, "locator": i.locator, "cas_verifiable": i.cas_verifiable}
                for i in self.items
            ],
            "entry_node_ids": list(self.entry_node_ids),
            "terminal_node_ids": list(self.terminal_node_ids),
            "provenance": {
                "sources": list(self.provenance.sources),
                "human_reviewed": self.provenance.human_reviewed,
                "notes": self.provenance.notes,
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CurriculumDAG:
        prov = data.get("provenance", {})
        return cls(
            version=data["version"],
            title=data["title"],
            nodes=tuple(
                Node(
                    id=n["id"],
                    title=n["title"],
                    sections=tuple(n["sections"]),
                    milestone_ids=tuple(n["milestone_ids"]),
                )
                for n in data["nodes"]
            ),
            edges=tuple((e[0], e[1]) for e in data["edges"]),
            milestones=tuple(
                Milestone(
                    id=m["id"],
                    node_id=m["node_id"],
                    summary=m["summary"],
                    objective_ids=tuple(m["objective_ids"]),
                    item_ids=tuple(m["item_ids"]),
                )
                for m in data["milestones"]
            ),
            objectives=tuple(
                LearningObjectiveRef(id=o["id"], section=o["section"], locator=o["locator"])
                for o in data["objectives"]
            ),
            items=tuple(
                ItemRef(id=i["id"], locator=i["locator"], cas_verifiable=bool(i["cas_verifiable"]))
                for i in data["items"]
            ),
            entry_node_ids=tuple(data["entry_node_ids"]),
            terminal_node_ids=tuple(data["terminal_node_ids"]),
            provenance=Provenance(
                sources=tuple(prov.get("sources", ())),
                human_reviewed=bool(prov.get("human_reviewed", False)),
                notes=prov.get("notes", ""),
            ),
        )
