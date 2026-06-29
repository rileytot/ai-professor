"""Tests for the verified Chapter 7 curriculum and the committed artifact."""

from __future__ import annotations

import json

from ai_professor.curriculum.ch7 import artifact_path, build_ch7_dag
from ai_professor.curriculum.dag import CurriculumDAG
from ai_professor.curriculum.qa_checks import check_curriculum

# A distinctive span of source LO prose that must not appear in the committed artifact (#7).
_DISTINCTIVE_LO_PROSE = "relative to different frames of reference"


def test_build_ch7_dag_passes_all_qa_checks() -> None:
    assert check_curriculum(build_ch7_dag()).ok


def test_ch7_shape() -> None:
    dag = build_ch7_dag()
    assert len(dag.nodes) == 4
    assert len(dag.objectives) == 8  # two LOs per section, four sections
    assert dag.entry_node_ids == ("work",)
    assert dag.terminal_node_ids == ("power",)
    # the human-verified non-linear cross-edge is present
    assert ("work", "work-energy-theorem") in dag.edges


def test_committed_artifact_is_in_sync_with_builder() -> None:
    on_disk = json.loads(artifact_path().read_text(encoding="utf-8"))
    assert on_disk == build_ch7_dag().to_dict()


def test_committed_artifact_round_trips_and_passes_qa() -> None:
    restored = CurriculumDAG.from_dict(json.loads(artifact_path().read_text(encoding="utf-8")))
    assert check_curriculum(restored).ok


def test_committed_artifact_objectives_carry_only_locators() -> None:
    # Invariant #7 structural guard: objectives/items hold locators, never LO/problem text.
    data = json.loads(artifact_path().read_text(encoding="utf-8"))
    for obj in data["objectives"]:
        assert set(obj) == {"id", "section", "locator"}
        assert "OpenStax" in obj["locator"]
    for item in data["items"]:
        assert set(item) == {"id", "locator", "cas_verifiable"}


def test_committed_artifact_omits_distinctive_lo_prose() -> None:
    assert _DISTINCTIVE_LO_PROSE not in artifact_path().read_text(encoding="utf-8")
