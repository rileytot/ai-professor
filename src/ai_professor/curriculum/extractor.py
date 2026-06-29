"""The extractor (curriculum-generation) context: cluster LOs into nodes + propose edges.

This is the ONLY generative act in v1 DAG construction (DESIGN.md §12): the model proposes a
clustering of the section learning objectives into gateable nodes and proposes prerequisite edges.
A human verifies the proposal -- it is not authoritative until reviewed (the verified result is what
``ch7.py`` encodes). Single-sample is acceptable here *because* a human verifies the small,
standardized output, not because the model is trusted to own coverage (invariant #4).

Prompting follows the evidence-backed standards in CLAUDE.md: clear decomposed instructions,
chain-of-thought, XML-tagged output; no persona padding. The model is told it may only organize the
objectives it is given -- never invent objectives or content.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass

from ai_professor.provider.adapter import CompletionRequest, LLMProvider, Message


class ExtractionError(Exception):
    """Raised when the model's proposal cannot be parsed into a structure."""


@dataclass(frozen=True, slots=True)
class ObjectiveInput:
    """One learning objective handed to the extractor (text is local, used only at build time)."""

    id: str
    section: str
    text: str


@dataclass(frozen=True, slots=True)
class ProposedNode:
    id: str
    title: str
    sections: tuple[str, ...]
    objective_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProposedStructure:
    """A model proposal awaiting human verification (not a curriculum until reviewed)."""

    nodes: tuple[ProposedNode, ...]
    edges: tuple[tuple[str, str], ...]
    rationale: str = ""


_SYSTEM = (
    "You organize a textbook chapter's section learning objectives into a prerequisite DAG. "
    "You cluster the GIVEN objectives into gateable nodes and propose prerequisite edges between "
    "nodes. You never invent objectives or content -- you only organize what you are given. "
    "A human reviewer verifies your proposal, so be explicit and conservative."
)


def build_extraction_prompt(objectives: Sequence[ObjectiveInput]) -> list[Message]:
    """Build the (system, user) messages asking for an XML-tagged clustering + edge proposal."""
    listed = "\n".join(
        f'<objective id="{o.id}" section="{o.section}">{o.text}</objective>' for o in objectives
    )
    user = (
        f"<objectives>\n{listed}\n</objectives>\n\n"
        "Task:\n"
        "1. In <analysis>, reason step by step about which objectives form coherent gateable nodes "
        "and what the prerequisite relationships are. The chapter's reading order is the default "
        "spine; propose a non-linear cross-edge ONLY where a node depends on more than its "
        "immediate predecessor.\n"
        '2. Then output a <curriculum> block: one <node id="slug" title="..."> per node, each '
        'containing a <objective ref="ID"/> for every objective it covers, and a <edge from="slug" '
        'to="slug"/> for each prerequisite edge.\n'
        "Use the exact objective ids given. Every objective must appear in exactly one node."
    )
    return [Message(role="system", content=_SYSTEM), Message(role="user", content=user)]


def _section_of(ref: str) -> str:
    return ref.split("-lo-")[0] if "-lo-" in ref else ""


def _block(text: str, tag: str) -> str:
    start, close = text.find(f"<{tag}"), text.find(f"</{tag}>")
    if start == -1 or close == -1:
        return ""
    return text[start : close + len(f"</{tag}>")]


def parse_structure(text: str) -> ProposedStructure:
    """Parse the model output's <curriculum> block into a ``ProposedStructure``."""
    curriculum = _block(text, "curriculum")
    if not curriculum:
        raise ExtractionError("no <curriculum> block in model output")
    try:
        root = ET.fromstring(curriculum)
    except ET.ParseError as exc:
        raise ExtractionError(f"invalid curriculum XML: {exc}") from exc
    nodes: list[ProposedNode] = []
    for nel in root.findall("node"):
        objective_ids = tuple(o.get("ref") or "" for o in nel.findall("objective"))
        sections = tuple(sorted({_section_of(r) for r in objective_ids if _section_of(r)}))
        nodes.append(
            ProposedNode(
                id=nel.get("id") or "",
                title=nel.get("title") or "",
                sections=sections,
                objective_ids=objective_ids,
            )
        )
    edges = tuple((e.get("from") or "", e.get("to") or "") for e in root.findall("edge"))
    analysis = _block(text, "analysis")
    return ProposedStructure(nodes=tuple(nodes), edges=edges, rationale=analysis)


def propose_structure(
    provider: LLMProvider, objectives: Sequence[ObjectiveInput], *, model: str | None = None
) -> ProposedStructure:
    """Ask the model to propose a node clustering + edges. The result MUST be human-verified."""
    request = CompletionRequest(messages=build_extraction_prompt(objectives), model=model)
    return parse_structure(provider.complete(request).text)
