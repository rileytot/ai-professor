"""Tests for the extractor: prompt construction, XML parsing, and provider wiring (mocked)."""

from __future__ import annotations

import pytest

from ai_professor.curriculum.extractor import (
    ExtractionError,
    ObjectiveInput,
    ProposedStructure,
    build_extraction_prompt,
    parse_structure,
    propose_structure,
)
from ai_professor.provider.adapter import Completion, CompletionRequest, LLMProvider

_OBJS = [
    ObjectiveInput(id="7.1-lo-1", section="7.1", text="Represent the work done by any force"),
    ObjectiveInput(id="7.2-lo-1", section="7.2", text="Calculate the kinetic energy of a particle"),
]

_XML = """
<analysis>7.1 (work) should precede 7.2 (kinetic energy).</analysis>
<curriculum>
  <node id="work" title="Work"><objective ref="7.1-lo-1"/></node>
  <node id="kinetic-energy" title="Kinetic Energy"><objective ref="7.2-lo-1"/></node>
  <edge from="work" to="kinetic-energy"/>
</curriculum>
"""


class _FixedBackend:
    name = "fixed"

    def __init__(self, text: str) -> None:
        self._text = text

    def available(self) -> bool:
        return True

    def complete(self, request: CompletionRequest) -> Completion:
        return Completion(text=self._text, model="m", backend=self.name)


def test_build_prompt_lists_objectives_and_asks_for_xml() -> None:
    messages = build_extraction_prompt(_OBJS)
    assert messages[0].role == "system"
    user = messages[1].content
    assert "7.1-lo-1" in user
    assert "Represent the work done by any force" in user
    assert "<curriculum>" in user  # output format is pinned


def test_parse_structure_extracts_nodes_edges_and_rationale() -> None:
    structure = parse_structure(_XML)
    assert {n.id for n in structure.nodes} == {"work", "kinetic-energy"}
    work = next(n for n in structure.nodes if n.id == "work")
    assert work.objective_ids == ("7.1-lo-1",)
    assert work.sections == ("7.1",)  # derived from the objective id
    assert ("work", "kinetic-energy") in structure.edges
    assert "kinetic energy" in structure.rationale


def test_parse_structure_without_block_raises() -> None:
    with pytest.raises(ExtractionError):
        parse_structure("the model said something but produced no curriculum block")


def test_parse_structure_invalid_xml_raises() -> None:
    with pytest.raises(ExtractionError):
        parse_structure("<curriculum><node id='x'></curriculum>")  # unclosed node


def test_propose_structure_uses_the_provider() -> None:
    provider = LLMProvider([_FixedBackend(_XML)])
    structure = propose_structure(provider, _OBJS)
    assert isinstance(structure, ProposedStructure)
    assert len(structure.nodes) == 2
