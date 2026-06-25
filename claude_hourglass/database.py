from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, Optional

from .models import UsageSnapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_snapshots (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at             TEXT NOT NULL,
    session_id              TEXT,
    model_display_name      TEXT,
    five_hour_used_pct      REAL,
    five_hour_resets_at     TEXT,
    seven_day_used_pct      REAL,
    seven_day_resets_at     TEXT,
    total_cost_usd          REAL,
    context_window_current  INTEGER,
    version                 TEXT,
    raw_json                TEXT,
    created_at              TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_captured_at ON usage_snapshots(captured_at);
CREATE INDEX IF NOT EXISTS idx_session_id  ON usage_snapshots(session_id);
"""


@contextmanager
def _conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init(db_path: Path) -> None:
    with _conn(db_path) as con:
        con.executescript(SCHEMA)


def insert(db_path: Path, snapshot: UsageSnapshot) -> int:
    sql = """
        INSERT INTO usage_snapshots
            (captured_at, session_id, model_display_name,
             five_hour_used_pct, five_hour_resets_at,
             seven_day_used_pct, seven_day_resets_at,
             total_cost_usd, context_window_current, version, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """
    with _conn(db_path) as con:
        cur = con.execute(sql, (
            snapshot.captured_at,
            snapshot.session_id,
            snapshot.model_display_name,
            snapshot.five_hour_used_pct,
            snapshot.five_hour_resets_at,
            snapshot.seven_day_used_pct,
            snapshot.seven_day_resets_at,
            snapshot.total_cost_usd,
            snapshot.context_window_current,
            snapshot.version,
            snapshot.raw_json,
        ))
        return cur.lastrowid  # type: ignore[return-value]


def latest(db_path: Path) -> Optional[UsageSnapshot]:
    sql = "SELECT * FROM usage_snapshots ORDER BY captured_at DESC LIMIT 1"
    with _conn(db_path) as con:
        row = con.execute(sql).fetchone()
    return _row_to_snapshot(row) if row else None


def recent(db_path: Path, days: int = 7) -> list[UsageSnapshot]:
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    sql = """
        SELECT * FROM usage_snapshots
        WHERE captured_at >= ?
        ORDER BY captured_at ASC
    """
    with _conn(db_path) as con:
        rows = con.execute(sql, (since,)).fetchall()
    return [_row_to_snapshot(r) for r in rows]


def by_session(db_path: Path, session_id: str) -> list[UsageSnapshot]:
    sql = "SELECT * FROM usage_snapshots WHERE session_id=? ORDER BY captured_at ASC"
    with _conn(db_path) as con:
        rows = con.execute(sql, (session_id,)).fetchall()
    return [_row_to_snapshot(r) for r in rows]


def sessions(db_path: Path, limit: int = 30) -> list[str]:
    sql = """
        SELECT DISTINCT session_id FROM usage_snapshots
        WHERE session_id IS NOT NULL
        ORDER BY MAX(captured_at) DESC
        LIMIT ?
    """
    with _conn(db_path) as con:
        rows = con.execute(sql, (limit,)).fetchall()
    return [r[0] for r in rows]


def _row_to_snapshot(row: sqlite3.Row) -> UsageSnapshot:
    d = dict(row)
    return UsageSnapshot(
        id=d["id"],
        captured_at=d["captured_at"],
        session_id=d.get("session_id"),
        model_display_name=d.get("model_display_name"),
        five_hour_used_pct=d.get("five_hour_used_pct"),
        five_hour_resets_at=d.get("five_hour_resets_at"),
        seven_day_used_pct=d.get("seven_day_used_pct"),
        seven_day_resets_at=d.get("seven_day_resets_at"),
        total_cost_usd=d.get("total_cost_usd"),
        context_window_current=d.get("context_window_current"),
        version=d.get("version"),
        raw_json=d.get("raw_json"),
    )
