from __future__ import annotations

import getpass
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.config import DB_PATH, ensure_data_dirs


SCHEMA = """
CREATE TABLE IF NOT EXISTS operation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    record_id TEXT,
    month TEXT,
    created_at TEXT NOT NULL,
    details_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL
);
"""

EVENT_TYPES = {
    "IMPORT",
    "DELETE",
    "RESTORE",
    "INTEGRITY_CHECK",
    "HOUSEKEEP",
    "ARCHIVE_CREATED",
}


def connect() -> sqlite3.Connection:
    ensure_data_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def actor_name() -> str:
    return os.environ.get("EV_ACTOR") or getpass.getuser()


def log_operation(
    *,
    action: str,
    status: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    details: dict[str, Any] | None = None,
    actor: str | None = None,
) -> int:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO operation_log (
                occurred_at,
                actor,
                action,
                target_type,
                target_id,
                status,
                details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                actor or actor_name(),
                action,
                target_type,
                str(target_id) if target_id is not None else None,
                status,
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def append_audit_event(
    *,
    event_type: str,
    record_id: str | int | None = None,
    month: str | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    event_type = event_type.upper()
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported audit event type: {event_type}")

    created_at = _now()
    details_json = json.dumps(details or {}, ensure_ascii=False, sort_keys=True)
    with connect() as conn:
        previous_hash = _last_event_hash(conn)
        event_hash = _event_hash(previous_hash, created_at, event_type, details_json)
        cursor = conn.execute(
            """
            INSERT INTO audit_events (
                event_type,
                record_id,
                month,
                created_at,
                details_json,
                previous_hash,
                event_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                str(record_id) if record_id is not None else None,
                month,
                created_at,
                details_json,
                previous_hash,
                event_hash,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_operations(
    *,
    limit: int = 50,
    action: str | None = None,
    status: str | None = None,
) -> list[sqlite3.Row]:
    clauses = []
    values: list[Any] = []
    if action:
        clauses.append("action = ?")
        values.append(action)
    if status:
        clauses.append("status = ?")
        values.append(status)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(limit)
    with connect() as conn:
        return list(
            conn.execute(
                f"""
                SELECT *
                FROM operation_log
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                values,
            )
        )


def list_audit_events(
    *,
    limit: int | None = 50,
    month: str | None = None,
) -> list[sqlite3.Row]:
    clauses = []
    values: list[Any] = []
    if month:
        clauses.append("month = ?")
        values.append(month)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        values.append(limit)
    with connect() as conn:
        return list(
            conn.execute(
                f"""
                SELECT *
                FROM audit_events
                {where}
                ORDER BY id DESC
                {limit_clause}
                """,
                values,
            )
        )


def count_audit_events(month: str | None = None) -> int:
    clause = "WHERE month = ?" if month else ""
    values = (month,) if month else ()
    with connect() as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM audit_events {clause}", values).fetchone()[0])


def _last_event_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
    return row["event_hash"] if row else ""


def _event_hash(previous_hash: str, created_at: str, event_type: str, details_json: str) -> str:
    payload = f"{previous_hash}{created_at}{event_type}{details_json}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
