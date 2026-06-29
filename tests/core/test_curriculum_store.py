"""Tests for the immutable-per-version curriculum store (store 1)."""

from __future__ import annotations

import sqlite3

import pytest

from ai_professor.core.errors import CurriculumImmutableError
from ai_professor.core.stores import Stores


def test_put_get_round_trip(stores: Stores) -> None:
    data = {"nodes": ["7.1", "7.2"], "edges": [["7.1", "7.2"]]}
    stores.curriculum.put("v1", data)
    assert stores.curriculum.get("v1") == data


def test_put_identical_is_idempotent(stores: Stores) -> None:
    data = {"a": 1}
    stores.curriculum.put("v1", data)
    stores.curriculum.put("v1", data)  # no error
    assert stores.curriculum.get("v1") == data


def test_put_changed_content_raises(stores: Stores) -> None:
    stores.curriculum.put("v1", {"a": 1})
    with pytest.raises(CurriculumImmutableError):
        stores.curriculum.put("v1", {"a": 2})


def test_get_missing_raises_keyerror(stores: Stores) -> None:
    with pytest.raises(KeyError):
        stores.curriculum.get("absent")


def test_versions_sorted(stores: Stores) -> None:
    stores.curriculum.put("v2", {})
    stores.curriculum.put("v1", {})
    assert stores.curriculum.versions() == ["v1", "v2"]


def test_update_blocked_by_trigger(stores: Stores) -> None:
    stores.curriculum.put("v1", {"a": 1})
    with pytest.raises(sqlite3.Error, match="immutable"):
        stores.conn.execute("UPDATE curriculum SET data = '{}' WHERE version = 'v1'")


def test_delete_blocked_by_trigger(stores: Stores) -> None:
    stores.curriculum.put("v1", {"a": 1})
    with pytest.raises(sqlite3.Error, match="immutable"):
        stores.conn.execute("DELETE FROM curriculum WHERE version = 'v1'")
