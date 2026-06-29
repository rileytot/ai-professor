"""Deterministic curriculum QA checks (DESIGN.md §8).

"Faithful execution makes pre-flight mechanical checks high-leverage": these catch a whole class
of structural hallucinations for free, before any learner touches the curriculum. They are pure
functions over the DAG -- no LLM, no network. What is *not* mechanically checkable (true
completeness, pedagogical ordering quality) is where human/expert review is spent.

The checks (one per DESIGN.md §8 bullet):
1. acyclic            -- the prerequisite graph has no cycle
2. integrity          -- edges/milestones/objectives/items reference things that exist
3. reachable          -- every node is reachable from an entry node
4. terminal           -- the declared terminal(s) exist and are reachable
5. cas_item           -- every milestone has >=1 sourced item with a CAS-verifiable answer
6. orphan             -- no node is disconnected (no prereq and no successor)
7. lo_coverage        -- every learning objective maps to a node (the v1 completeness check)
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ai_professor.curriculum.dag import CurriculumDAG
from ai_professor.curriculum.graph import Adjacency, build_adjacency, find_cycle, reachable_from


@dataclass(frozen=True, slots=True)
class QAViolation:
    check: str
    detail: str


@dataclass(frozen=True, slots=True)
class QAReport:
    violations: tuple[QAViolation, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    def by_check(self, check: str) -> tuple[QAViolation, ...]:
        return tuple(v for v in self.violations if v.check == check)


def _check_acyclic(dag: CurriculumDAG, adj: Adjacency) -> list[QAViolation]:
    cycle = find_cycle(adj)
    if cycle is not None:
        return [QAViolation("acyclic", "prerequisite cycle: " + " -> ".join(cycle))]
    return []


def _check_integrity(dag: CurriculumDAG) -> list[QAViolation]:
    out: list[QAViolation] = []
    nodes, milestones = dag.node_ids, dag.milestone_ids
    objectives, items = dag.objective_ids, dag.item_ids
    for src, dst in dag.edges:
        for end in (src, dst):
            if end not in nodes:
                out.append(QAViolation("integrity", f"edge references unknown node {end!r}"))
    for node in dag.nodes:
        for mid in node.milestone_ids:
            if mid not in milestones:
                out.append(
                    QAViolation("integrity", f"node {node.id!r} -> unknown milestone {mid!r}")
                )
    for m in dag.milestones:
        if m.node_id not in nodes:
            out.append(
                QAViolation("integrity", f"milestone {m.id!r} on unknown node {m.node_id!r}")
            )
        for oid in m.objective_ids:
            if oid not in objectives:
                out.append(
                    QAViolation("integrity", f"milestone {m.id!r} -> unknown objective {oid!r}")
                )
        for iid in m.item_ids:
            if iid not in items:
                out.append(QAViolation("integrity", f"milestone {m.id!r} -> unknown item {iid!r}"))
    return out


def _check_reachable(dag: CurriculumDAG, adj: Adjacency) -> list[QAViolation]:
    if not dag.entry_node_ids:
        return [QAViolation("reachable", "no entry nodes declared")]
    reached = reachable_from(adj, dag.entry_node_ids)
    return [
        QAViolation("reachable", f"node {nid!r} is not reachable from any entry node")
        for nid in sorted(dag.node_ids - reached)
    ]


def _check_terminal(dag: CurriculumDAG, adj: Adjacency) -> list[QAViolation]:
    out: list[QAViolation] = []
    if not dag.terminal_node_ids:
        out.append(QAViolation("terminal", "no terminal nodes declared"))
    reached = reachable_from(adj, dag.entry_node_ids) if dag.entry_node_ids else frozenset()
    for tid in dag.terminal_node_ids:
        if tid not in dag.node_ids:
            out.append(QAViolation("terminal", f"terminal {tid!r} is not a node"))
        elif tid not in reached:
            out.append(QAViolation("terminal", f"terminal {tid!r} is not reachable from entry"))
    return out


def _check_cas_items(dag: CurriculumDAG) -> list[QAViolation]:
    out: list[QAViolation] = []
    for m in dag.milestones:
        if not any((it := dag.item(iid)) is not None and it.cas_verifiable for iid in m.item_ids):
            out.append(
                QAViolation("cas_item", f"milestone {m.id!r} has no CAS-verifiable sourced item")
            )
    return out


def _check_orphans(dag: CurriculumDAG, adj: Adjacency) -> list[QAViolation]:
    if len(dag.nodes) <= 1:
        return []
    indegree = dict.fromkeys(dag.node_ids, 0)
    for _src, dst in dag.edges:
        if dst in indegree:
            indegree[dst] += 1
    return [
        QAViolation("orphan", f"node {n.id!r} has no prerequisite or successor edges")
        for n in dag.nodes
        if indegree.get(n.id, 0) == 0 and not adj.get(n.id, frozenset())
    ]


def _check_lo_coverage(dag: CurriculumDAG) -> list[QAViolation]:
    mapped: set[str] = set()
    for m in dag.milestones:
        mapped.update(m.objective_ids)
    return [
        QAViolation("lo_coverage", f"learning objective {oid!r} maps to no milestone")
        for oid in sorted(dag.objective_ids - mapped)
    ]


def check_curriculum(dag: CurriculumDAG) -> QAReport:
    """Run all deterministic QA checks and return every violation found."""
    adj = build_adjacency((n.id for n in dag.nodes), dag.edges)
    violations: list[QAViolation] = [
        *_check_acyclic(dag, adj),
        *_check_integrity(dag),
        *_check_reachable(dag, adj),
        *_check_terminal(dag, adj),
        *_check_cas_items(dag),
        *_check_orphans(dag, adj),
        *_check_lo_coverage(dag),
    ]
    return QAReport(tuple(violations))


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: validate a curriculum JSON file. Exit 0 if it passes, 1 if not, 2 on usage error."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m ai_professor.curriculum.qa_checks <curriculum.json>")
        return 2
    dag = CurriculumDAG.from_dict(json.loads(Path(args[0]).read_text(encoding="utf-8")))
    report = check_curriculum(dag)
    if report.ok:
        print(f"OK: curriculum {dag.version!r} passed all QA checks ({len(dag.nodes)} nodes)")
        return 0
    for v in report.violations:
        print(f"FAIL [{v.check}] {v.detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
