"""Ingest OpenStax section content (the human-authored completeness spec).

The textbook's section learning objectives ("By the end of this section, you will be able to: ...")
are the grounding for the DAG's *structure* (DESIGN.md §4.2, §12): chapter/section order gives the
first-pass hierarchy, and the LO set is what the completeness check is measured against.

Parsing is pure and unit-tested on a real fixture; fetching is a thin, injectable layer. Per
invariant #7, only LO *locators* go into the shareable curriculum; the LO *text* returned here is
written to the local, git-ignored ``content/`` store for runtime rehydration (with attribution).
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass

import httpx

BOOK_BASE = "https://openstax.org/books/university-physics-volume-1/pages/"
USER_AGENT = "ai-professor/0.0 (curriculum ingest; CC-BY OpenStax)"
_MARKER = "by the end of this section, you will be able to"
_DEFAULT_TIMEOUT_S = 30.0


@dataclass(frozen=True, slots=True)
class SectionContent:
    """Ingested content for one section. ``learning_objectives`` is verbatim source text."""

    section: str  # e.g. "7.1"
    slug: str  # e.g. "7-1-work"
    learning_objectives: tuple[str, ...]


def _clean(fragment: str) -> str:
    """Strip inline tags, collapse whitespace, and unescape HTML entities."""
    no_tags = re.sub(r"<[^>]+>", "", fragment)
    return _html.unescape(" ".join(no_tags.split()))


def parse_learning_objectives(page_html: str) -> list[str]:
    """Extract the section's learning objectives: the <li> items of the <ul> after the LO marker."""
    idx = page_html.lower().find(_MARKER)
    if idx == -1:
        return []
    ul = re.search(r"<ul\b[^>]*>(.*?)</ul>", page_html[idx:], re.DOTALL | re.IGNORECASE)
    if ul is None:
        return []
    items = re.findall(r"<li\b[^>]*>(.*?)</li>", ul.group(1), re.DOTALL | re.IGNORECASE)
    return [text for raw in items if (text := _clean(raw))]


def fetch_section_html(slug: str, *, client: httpx.Client | None = None) -> str:
    """GET a section page's HTML (injectable client for tests)."""
    url = BOOK_BASE + slug
    headers = {"User-Agent": USER_AGENT}
    if client is not None:
        return client.get(url, headers=headers).text
    with httpx.Client(timeout=_DEFAULT_TIMEOUT_S, follow_redirects=True) as owned:
        return owned.get(url, headers=headers).text


def ingest_section(
    section: str, slug: str, *, client: httpx.Client | None = None
) -> SectionContent:
    """Fetch and parse one section into its learning objectives."""
    html = fetch_section_html(slug, client=client)
    return SectionContent(
        section=section,
        slug=slug,
        learning_objectives=tuple(parse_learning_objectives(html)),
    )
