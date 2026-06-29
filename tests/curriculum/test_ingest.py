"""Tests for OpenStax content ingestion (pure parsing on a real fixture; fetch via a mock)."""

from __future__ import annotations

import httpx

from ai_professor.curriculum.ingest import (
    SectionContent,
    ingest_section,
    parse_learning_objectives,
)

# A faithful slice of the real OpenStax §7.1 page structure (server-rendered HTML).
_FIXTURE = """
<header><h3>Learning Objectives</h3></header><section>
<p id="para-00001">By the end of this section, you will be able to:</p>
<ul id="list-00001">
<li>Represent the work done by any force</li>
<li>Evaluate the work done for various <span data-type="term" id="t1">forces</span></li>
</ul></section>
<p>In physics, work is done on an object when energy is transferred...</p>
"""


def test_parse_learning_objectives_extracts_and_cleans() -> None:
    los = parse_learning_objectives(_FIXTURE)
    assert los == [
        "Represent the work done by any force",
        "Evaluate the work done for various forces",  # inline <span> stripped
    ]


def test_parse_learning_objectives_no_marker_returns_empty() -> None:
    assert parse_learning_objectives("<p>no objectives here</p>") == []


def test_ingest_section_uses_injected_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("7-1-work")
        return httpx.Response(200, text=_FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sc = ingest_section("7.1", "7-1-work", client=client)
    assert isinstance(sc, SectionContent)
    assert sc.section == "7.1"
    assert len(sc.learning_objectives) == 2
