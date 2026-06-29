"""Shared test fixtures."""

from __future__ import annotations

import pytest

from ai_professor.core.stores import Stores, open_stores


class FixedClock:
    """Deterministic clock for tests."""

    def __init__(self, value: str = "2026-01-01T00:00:00+00:00") -> None:
        self._value = value

    def now_iso(self) -> str:
        return self._value


@pytest.fixture
def stores() -> Stores:
    """Fresh in-memory three-store database with a deterministic clock."""
    return open_stores(":memory:", clock=FixedClock())
