"""Tests for the append-only event log (store 3)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ai_professor.core.errors import IntegrityError
from ai_professor.core.events import (
    AnswerSubmitted,
    MilestoneConfirmed,
    ProblemServed,
    TopicAdvanced,
    TopicStarted,
)
from ai_professor.core.stores import EventLog, Stores, open_stores


def test_append_assigns_increasing_seq(stores: Stores) -> None:
    a = stores.events.append(TopicStarted(node_id="7.1"))
    b = stores.events.append(
        AnswerSubmitted(node_id="7.1", item_id="i", variant_seed=1, correct=True)
    )
    assert (a.seq, b.seq) == (1, 2)
    assert stores.events.latest_seq() == 2


def test_read_returns_events_in_order(stores: Stores) -> None:
    stores.events.append(TopicStarted(node_id="7.1"))
    stores.events.append(ProblemServed(node_id="7.1", item_id="i", variant_seed=7))
    recs = stores.events.read()
    assert [r.seq for r in recs] == [1, 2]
    assert isinstance(recs[0].event, TopicStarted)
    assert isinstance(recs[1].event, ProblemServed)


def test_all_event_types_round_trip(stores: Stores) -> None:
    originals = [
        TopicStarted(node_id="7.1"),
        ProblemServed(node_id="7.1", item_id="i", variant_seed=42),
        AnswerSubmitted(node_id="7.1", item_id="i", variant_seed=42, correct=False),
        MilestoneConfirmed(milestone_id="m1", node_id="7.1", proof_id="p1"),
        TopicAdvanced(from_node="7.1", to_node="7.2"),
    ]
    for ev in originals:
        stores.events.append(ev)
    read_back = [r.event for r in stores.events.read()]
    assert read_back == originals  # frozen dataclasses compare by value


def test_read_up_to_seq_filters(stores: Stores) -> None:
    for _ in range(3):
        stores.events.append(TopicStarted(node_id="7.1"))
    assert [r.seq for r in stores.events.read(up_to_seq=2)] == [1, 2]


def test_read_by_stream(stores: Stores) -> None:
    stores.events.append(TopicStarted(node_id="a"), stream="alice")
    stores.events.append(TopicStarted(node_id="b"), stream="bob")
    alice = stores.events.read(stream="alice")
    assert len(alice) == 1
    assert isinstance(alice[0].event, TopicStarted)
    assert alice[0].event.node_id == "a"


def test_update_blocked_by_trigger(stores: Stores) -> None:
    stores.events.append(TopicStarted(node_id="7.1"))
    # Even raw SQL cannot mutate the log: the storage engine rejects it.
    with pytest.raises(sqlite3.Error, match="append-only"):
        stores.conn.execute("UPDATE events SET stream = 'x' WHERE seq = 1")


def test_delete_blocked_by_trigger(stores: Stores) -> None:
    stores.events.append(TopicStarted(node_id="7.1"))
    with pytest.raises(sqlite3.Error, match="append-only"):
        stores.conn.execute("DELETE FROM events WHERE seq = 1")


def test_log_api_has_no_mutation_methods() -> None:
    # The append-only property is also reflected in the API surface: no update/delete.
    assert not hasattr(EventLog, "update")
    assert not hasattr(EventLog, "delete")


def test_insert_or_replace_is_blocked(stores: Stores) -> None:
    # INSERT OR REPLACE's conflict-delete skips BEFORE DELETE triggers; a BEFORE INSERT guard
    # blocks the upsert so it cannot silently overwrite a recorded event.
    stores.events.append(MilestoneConfirmed(milestone_id="m1", node_id="7.1", proof_id="p1"))
    with pytest.raises(sqlite3.Error, match="append-only"):
        stores.conn.execute(
            "INSERT OR REPLACE INTO events(seq, stream, ts, type, payload) "
            "VALUES (1, 'default', 't', 'MilestoneConfirmed', '{\"milestone_id\": \"forged\", "
            '"node_id": "7.1", "proof_id": "x"}\')'
        )


def test_connect_detects_stripped_guard_triggers(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    first = open_stores(db)
    first.events.append(TopicStarted(node_id="7.1"))
    first.conn.execute("DROP TRIGGER events_no_update")  # DDL: triggers cannot block this
    first.conn.commit()
    first.conn.close()
    # Reopening detects the stripped guard rather than silently restoring it.
    with pytest.raises(IntegrityError):
        open_stores(db)
