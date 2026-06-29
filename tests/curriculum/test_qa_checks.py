"""Tests for the deterministic curriculum QA checks (one negative case per check)."""

from __future__ import annotations

from dataclasses import replace

from ai_professor.curriculum.dag import (
    CurriculumDAG,
    ItemRef,
    LearningObjectiveRef,
    Milestone,
    Node,
    Provenance,
)
from ai_professor.curriculum.qa_checks import check_curriculum


def _valid_dag() -> CurriculumDAG:
    """A small, fully-consistent two-node curriculum: a (entry) -> b (terminal)."""
    return CurriculumDAG(
        version="test-v1",
        title="Test",
        nodes=(
            Node(id="a", title="A", sections=("1.1",), milestone_ids=("m_a",)),
            Node(id="b", title="B", sections=("1.2",), milestone_ids=("m_b",)),
        ),
        edges=(("a", "b"),),
        milestones=(
            Milestone(
                id="m_a", node_id="a", summary="do a", objective_ids=("o1",), item_ids=("i1",)
            ),
            Milestone(
                id="m_b", node_id="b", summary="do b", objective_ids=("o2",), item_ids=("i2",)
            ),
        ),
        objectives=(
            LearningObjectiveRef(id="o1", section="1.1", locator="src 1.1 lo1"),
            LearningObjectiveRef(id="o2", section="1.2", locator="src 1.2 lo1"),
        ),
        items=(
            ItemRef(id="i1", locator="src 1.1 p1", cas_verifiable=True),
            ItemRef(id="i2", locator="src 1.2 p1", cas_verifiable=True),
        ),
        entry_node_ids=("a",),
        terminal_node_ids=("b",),
        provenance=Provenance(sources=("test",), human_reviewed=True),
    )


def test_valid_dag_passes_all_checks() -> None:
    assert check_curriculum(_valid_dag()).ok


def test_cycle_is_flagged() -> None:
    dag = replace(_valid_dag(), edges=(("a", "b"), ("b", "a")))
    assert check_curriculum(dag).by_check("acyclic")


def test_dangling_reference_is_flagged() -> None:
    dag = _valid_dag()
    bad = replace(
        dag,
        milestones=(
            replace(dag.milestones[0], objective_ids=("o1", "does-not-exist")),
            dag.milestones[1],
        ),
    )
    assert check_curriculum(bad).by_check("integrity")


def test_unreachable_node_is_flagged() -> None:
    dag = _valid_dag()
    # add c -> b; nothing leads to c, so c is unreachable from entry a (but not an orphan)
    bad = replace(
        dag,
        nodes=(*dag.nodes, Node(id="c", title="C", sections=("1.3",), milestone_ids=())),
        edges=(*dag.edges, ("c", "b")),
    )
    assert check_curriculum(bad).by_check("reachable")


def test_unreachable_or_missing_terminal_is_flagged() -> None:
    dag = replace(_valid_dag(), terminal_node_ids=("not-a-node",))
    assert check_curriculum(dag).by_check("terminal")


def test_milestone_without_cas_item_is_flagged() -> None:
    dag = _valid_dag()
    bad = replace(dag, items=(dag.items[0], replace(dag.items[1], cas_verifiable=False)))
    assert check_curriculum(bad).by_check("cas_item")


def test_orphan_node_is_flagged() -> None:
    dag = _valid_dag()
    bad = replace(dag, nodes=(*dag.nodes, Node(id="c", title="C", sections=(), milestone_ids=())))
    assert check_curriculum(bad).by_check("orphan")


def test_unmapped_learning_objective_is_flagged() -> None:
    dag = _valid_dag()
    bad = replace(
        dag,
        objectives=(*dag.objectives, LearningObjectiveRef(id="o3", section="1.3", locator="x")),
    )
    assert check_curriculum(bad).by_check("lo_coverage")


def test_round_trip_through_dict_preserves_validity() -> None:
    dag = _valid_dag()
    restored = CurriculumDAG.from_dict(dag.to_dict())
    assert restored == dag
    assert check_curriculum(restored).ok
