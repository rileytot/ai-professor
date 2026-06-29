"""The three distinct stores (DESIGN.md §7), on SQLite.

1. Curriculum     -- immutable per version.
2. Knowledge      -- derived projection (see ``core.projection``; not stored, folded on demand).
3. Event log      -- append-only audit trail.

They share one SQLite database but are logically distinct with different immutability needs.
**Mutation is blocked at the storage engine via triggers** (not just the Python API): raw
``UPDATE``, ``DELETE``, and ``INSERT OR REPLACE`` (whose conflict-delete does not fire BEFORE
DELETE triggers) against the event log or an existing curriculum version are all rejected. This
makes invariant #1's "append-only ledger" and §7's "immutable curriculum" deterministic
guarantees rather than conventions the caller must remember.

Honest limits: triggers cannot intercept DDL, so a ``DROP TABLE`` by a sufficiently privileged
caller can destroy a table wholesale -- but that is *loud* (the data is gone), not a *silent* edit
of a single record, which the triggers do prevent. ``connect`` additionally detects a database
whose guard triggers were stripped (the drop-triggers-then-mutate attack) and refuses to open it,
giving cross-session tamper-evidence. A hash-chained log for stronger, in-session tamper-evidence
is a post-v1 option.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ai_professor.core.errors import CurriculumImmutableError, IntegrityError
from ai_professor.core.events import DomainEvent, RecordedEvent, deserialize, serialize
from ai_professor.core.projection import KnowledgeProjection


class Clock(Protocol):
    """Minimal clock so timestamps can be made deterministic in tests."""

    def now_iso(self) -> str: ...


class SystemClock:
    """Wall-clock UTC, ISO-8601."""

    def now_iso(self) -> str:
        return datetime.now(UTC).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq     INTEGER PRIMARY KEY AUTOINCREMENT,
    stream  TEXT NOT NULL,
    ts      TEXT NOT NULL,
    type    TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_stream ON events(stream, seq);

-- The event log is append-only: block mutation at the storage engine.
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
    BEGIN SELECT RAISE(ABORT, 'event log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
    BEGIN SELECT RAISE(ABORT, 'event log is append-only'); END;
-- ...and block INSERT OR REPLACE on an existing seq (its conflict-delete skips BEFORE DELETE).
-- Normal appends never specify seq, so NEW.seq is a fresh AUTOINCREMENT value that cannot collide.
CREATE TRIGGER IF NOT EXISTS events_no_replace BEFORE INSERT ON events
    WHEN EXISTS (SELECT 1 FROM events WHERE seq = NEW.seq)
    BEGIN SELECT RAISE(ABORT, 'event log is append-only'); END;

CREATE TABLE IF NOT EXISTS curriculum (
    version    TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    created_ts TEXT NOT NULL
);

-- A curriculum version is immutable once written: block mutation at the storage engine.
CREATE TRIGGER IF NOT EXISTS curriculum_no_update BEFORE UPDATE ON curriculum
    BEGIN SELECT RAISE(ABORT, 'curriculum is immutable per version'); END;
CREATE TRIGGER IF NOT EXISTS curriculum_no_delete BEFORE DELETE ON curriculum
    BEGIN SELECT RAISE(ABORT, 'curriculum is immutable per version'); END;
CREATE TRIGGER IF NOT EXISTS curriculum_no_replace BEFORE INSERT ON curriculum
    WHEN EXISTS (SELECT 1 FROM curriculum WHERE version = NEW.version)
    BEGIN SELECT RAISE(ABORT, 'curriculum is immutable per version'); END;
"""

# Guard triggers that must be present on a non-empty database (tamper-evidence; see connect()).
_EVENT_GUARDS = ("events_no_update", "events_no_delete", "events_no_replace")
_CURRICULUM_GUARDS = ("curriculum_no_update", "curriculum_no_delete", "curriculum_no_replace")


def _detect_tampering(conn: sqlite3.Connection) -> None:
    """Refuse to open a database whose tables exist but whose guard triggers were stripped.

    This catches the drop-triggers-then-mutate attack across sessions. We check *before* the
    schema is re-applied, since ``CREATE TRIGGER IF NOT EXISTS`` would otherwise silently restore
    the guards and mask the tampering.
    """
    rows = conn.execute("SELECT type, name FROM sqlite_master").fetchall()
    tables = {r["name"] for r in rows if r["type"] == "table"}
    triggers = {r["name"] for r in rows if r["type"] == "trigger"}
    missing: list[str] = []
    if "events" in tables:
        missing += [g for g in _EVENT_GUARDS if g not in triggers]
    if "curriculum" in tables:
        missing += [g for g in _CURRICULUM_GUARDS if g not in triggers]
    if missing:
        raise IntegrityError(f"guard triggers missing (possible tampering): {sorted(missing)}")


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a connection, verify guard-trigger integrity, and ensure the schema exists."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _detect_tampering(conn)
    conn.executescript(_SCHEMA)
    return conn


class EventLog:
    """Append-only event log (store 3).

    The public API exposes only ``append`` and read methods -- there is deliberately no update or
    delete. The SQLite triggers enforce the same property even against raw SQL UPDATE/DELETE and
    INSERT OR REPLACE.
    """

    def __init__(self, conn: sqlite3.Connection, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock = clock if clock is not None else SystemClock()

    def append(self, event: DomainEvent, *, stream: str = "default") -> RecordedEvent:
        """Append an event and return it with its assigned ``seq`` and timestamp."""
        type_name, payload = serialize(event)
        ts = self._clock.now_iso()
        cur = self._conn.execute(
            "INSERT INTO events(stream, ts, type, payload) VALUES (?, ?, ?, ?)",
            (stream, ts, type_name, json.dumps(payload)),
        )
        self._conn.commit()
        assert cur.lastrowid is not None  # guaranteed after a successful INSERT
        return RecordedEvent(seq=cur.lastrowid, stream=stream, ts=ts, event=event)

    def read(
        self, *, stream: str | None = None, up_to_seq: int | None = None
    ) -> list[RecordedEvent]:
        """Read events in append order, optionally filtered by stream and/or an upper seq bound."""
        sql = "SELECT seq, stream, ts, type, payload FROM events"
        clauses: list[str] = []
        params: list[Any] = []
        if stream is not None:
            clauses.append("stream = ?")
            params.append(stream)
        if up_to_seq is not None:
            clauses.append("seq <= ?")
            params.append(up_to_seq)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY seq ASC"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            RecordedEvent(
                seq=row["seq"],
                stream=row["stream"],
                ts=row["ts"],
                event=deserialize(row["type"], json.loads(row["payload"])),
            )
            for row in rows
        ]

    def latest_seq(self) -> int:
        """Highest assigned seq, or 0 if the log is empty."""
        row = self._conn.execute("SELECT MAX(seq) AS m FROM events").fetchone()
        return int(row["m"]) if row["m"] is not None else 0


class CurriculumStore:
    """Immutable-per-version curriculum store (store 1)."""

    def __init__(self, conn: sqlite3.Connection, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock = clock if clock is not None else SystemClock()

    def put(self, version: str, data: Mapping[str, Any]) -> None:
        """Store a curriculum version. Idempotent if identical; raises if it would change."""
        payload = json.dumps(data, sort_keys=True)
        existing = self._conn.execute(
            "SELECT data FROM curriculum WHERE version = ?", (version,)
        ).fetchone()
        if existing is not None:
            if existing["data"] == payload:
                return  # idempotent re-publish of identical content
            raise CurriculumImmutableError(version)
        self._conn.execute(
            "INSERT INTO curriculum(version, data, created_ts) VALUES (?, ?, ?)",
            (version, payload, self._clock.now_iso()),
        )
        self._conn.commit()

    def get(self, version: str) -> dict[str, Any]:
        """Return the stored curriculum for ``version`` (raises ``KeyError`` if absent)."""
        row = self._conn.execute(
            "SELECT data FROM curriculum WHERE version = ?", (version,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no curriculum version {version!r}")
        loaded: dict[str, Any] = json.loads(row["data"])
        return loaded

    def versions(self) -> list[str]:
        """All stored versions, sorted."""
        rows = self._conn.execute("SELECT version FROM curriculum ORDER BY version").fetchall()
        return [row["version"] for row in rows]


@dataclass
class Stores:
    """Facade bundling the three stores over one connection."""

    conn: sqlite3.Connection
    events: EventLog
    curriculum: CurriculumStore
    projection: KnowledgeProjection


def open_stores(path: str | Path = ":memory:", clock: Clock | None = None) -> Stores:
    """Open the three stores over a single SQLite database (in-memory by default)."""
    conn = connect(path)
    log = EventLog(conn, clock)
    return Stores(
        conn=conn,
        events=log,
        curriculum=CurriculumStore(conn, clock),
        projection=KnowledgeProjection(log),
    )
