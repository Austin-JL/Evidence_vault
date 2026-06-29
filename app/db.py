from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.config import DB_PATH, ensure_data_dirs


SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_date TEXT NOT NULL,
    direction TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    metadata_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    captured_at TEXT,
    imported_at TEXT NOT NULL,
    gps_lat REAL,
    gps_lng REAL,
    device_model TEXT,
    file_size INTEGER,
    mime_type TEXT,
    note TEXT
);

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


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    ensure_data_dirs()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_record(record: dict[str, Any]) -> int:
    columns = (
        "record_date",
        "direction",
        "original_filename",
        "stored_path",
        "metadata_path",
        "sha256",
        "captured_at",
        "imported_at",
        "gps_lat",
        "gps_lng",
        "device_model",
        "file_size",
        "mime_type",
        "note",
    )
    values = [record.get(column) for column in columns]
    placeholders = ", ".join("?" for _ in columns)
    with connect() as conn:
        cursor = conn.execute(
            f"INSERT INTO evidence_records ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        conn.commit()
        return int(cursor.lastrowid)


def find_by_sha256(file_hash: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(
            conn.execute(
                "SELECT * FROM evidence_records WHERE sha256 = ? ORDER BY imported_at",
                (file_hash,),
            )
        )


def get_record(record_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM evidence_records WHERE id = ?",
            (record_id,),
        ).fetchone()


def delete_record(record_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM evidence_records WHERE id = ?",
            (record_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def list_month(month: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(
            conn.execute(
                """
                SELECT * FROM evidence_records
                WHERE record_date >= ? AND record_date < ?
                ORDER BY record_date, direction, id
                """,
                (f"{month}-01", _next_month_start(month)),
            )
        )


def _next_month_start(month: str) -> str:
    year, month_num = [int(part) for part in month.split("-")]
    if month_num == 12:
        return f"{year + 1:04d}-01-01"
    return f"{year:04d}-{month_num + 1:02d}-01"
