from __future__ import annotations

import getpass
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
"""


def connect() -> sqlite3.Connection:
    ensure_data_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
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


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
