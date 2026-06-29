"""The verified Chapter 7 curriculum DAG ("Work and Kinetic Energy").

This is the v1 *extract-and-verify* artifact (DESIGN.md §12). The learning objectives are grounded
in the real OpenStax source (fetched + parsed by ``ingest``; see the 8 LOs below, two per section).
The *generative* act -- clustering the LOs into gateable nodes and proposing the non-linear
cross-edge -- is encoded here and human-verified: intro mechanics is the most standardized content
in physics pedagogy, so verification (the originator's strength) is most reliable here.

The committed JSON artifact (``curricula/univ_physics_v1_ch7.json``) is generated from this module
and holds **structure + locators only** (no copyrighted text -- invariant #7). Run ``python -m
ai_professor.curriculum.ch7`` to (re)generate it.

Cross-source diff (Ch 7 TOC vs MIT 8.01): work, kinetic energy, the work-energy theorem, and power
are the standard intro work/energy unit and appear in both. Potential energy / energy conservation
is OpenStax Ch 8 (out of this single-chapter slice). No omissions found within the Ch 7 scope.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ai_professor.curriculum.dag import (
    CurriculumDAG,
    ItemRef,
    LearningObjectiveRef,
    Milestone,
    Node,
    Provenance,
)

VERSION = "univ-physics-v1-ch7"
_SOURCE = "OpenStax University Physics Volume 1 (CC BY 4.0)"

# (section, [learning objectives]) -- verbatim LO text lives in local content, not here. These are
# the real objectives parsed from the source; only their ids/locators are committed.
_SECTIONS: tuple[tuple[str, str, int], ...] = (
    ("7.1", "Work", 2),
    ("7.2", "Kinetic Energy", 2),
    ("7.3", "Work-Energy Theorem", 2),
    ("7.4", "Power", 2),
)

# node id -> (title, section). One gateable node per section for this slice.
_NODES: tuple[tuple[str, str, str], ...] = (
    ("work", "Work", "7.1"),
    ("kinetic-energy", "Kinetic Energy", "7.2"),
    ("work-energy-theorem", "Work-Energy Theorem", "7.3"),
    ("power", "Power", "7.4"),
)

# Prerequisite edges. The spine is reading order (7.1->7.2->7.3->7.4); the human-verified
# non-linear cross-edge is work -> work-energy-theorem (the theorem needs BOTH work and KE).
_EDGES: tuple[tuple[str, str], ...] = (
    ("work", "kinetic-energy"),
    ("kinetic-energy", "work-energy-theorem"),
    ("work-energy-theorem", "power"),
    ("work", "work-energy-theorem"),  # cross-edge (verified)
)

_MILESTONE_SUMMARY: dict[str, str] = {
    "work": "Compute the work done by constant and variable forces.",
    "kinetic-energy": "Compute kinetic energy and evaluate it across reference frames.",
    "work-energy-theorem": "Apply the work-energy theorem in both directions (motion <-> forces).",
    "power": "Relate work over time to power and compute power for a force on a moving body.",
}


def build_ch7_dag() -> CurriculumDAG:
    """Construct the verified Chapter 7 curriculum DAG."""
    objectives: list[LearningObjectiveRef] = []
    for section, _title, n_los in _SECTIONS:
        for i in range(1, n_los + 1):
            objectives.append(
                LearningObjectiveRef(
                    id=f"{section}-lo-{i}",
                    section=section,
                    locator=(
                        f"OpenStax University Physics Vol. 1 §{section}, learning objective {i}"
                    ),
                )
            )

    nodes: list[Node] = []
    milestones: list[Milestone] = []
    items: list[ItemRef] = []
    for node_id, title, section in _NODES:
        milestone_id = f"m-{node_id}"
        item_id = f"{section}-item-1"
        # Placeholder sourced item: Phase 2 pins the specific problem(s) and attaches the numeric
        # template that makes the CAS-verifiable claim true with teeth.
        items.append(
            ItemRef(
                id=item_id,
                locator=f"OpenStax University Physics Vol. 1, Ch. 7 Problems (§{section} {title})",
                cas_verifiable=True,
            )
        )
        milestones.append(
            Milestone(
                id=milestone_id,
                node_id=node_id,
                summary=_MILESTONE_SUMMARY[node_id],
                objective_ids=tuple(o.id for o in objectives if o.section == section),
                item_ids=(item_id,),
            )
        )
        nodes.append(
            Node(id=node_id, title=title, sections=(section,), milestone_ids=(milestone_id,))
        )

    return CurriculumDAG(
        version=VERSION,
        title="University Physics Vol. 1, Ch. 7: Work and Kinetic Energy",
        nodes=tuple(nodes),
        edges=_EDGES,
        milestones=tuple(milestones),
        objectives=tuple(objectives),
        items=tuple(items),
        entry_node_ids=("work",),
        terminal_node_ids=("power",),
        provenance=Provenance(
            sources=(_SOURCE,),
            human_reviewed=True,
            notes=(
                "Extract-and-verify (DESIGN.md §12). LOs parsed from source; node clustering and "
                "the work->work-energy-theorem cross-edge human-verified. Cross-source diff vs "
                "MIT 8.01 found no omissions within Ch 7 scope. Sourced items + CAS templates are "
                "specified in Phase 2."
            ),
        ),
    )


def artifact_path() -> Path:
    return Path(__file__).resolve().parents[3] / "curricula" / f"{VERSION}.json"


def main(argv: list[str] | None = None) -> int:
    """Write the curriculum artifact JSON (structure + locators only)."""
    args = list(sys.argv[1:] if argv is None else argv)
    out = Path(args[0]) if args else artifact_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_ch7_dag().to_dict(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
