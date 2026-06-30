from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app import db
from app.config import PROJECT_ROOT, ensure_data_dirs
from app.hashing import sha256_file


@dataclass(frozen=True)
class IntegrityIssue:
    record_id: int
    severity: str
    message: str
    path: str | None = None


def check_month(month: str) -> dict[str, Any]:
    ensure_data_dirs()
    _validate_month(month)
    rows = db.list_month(month)
    issues: list[IntegrityIssue] = []
    seen_paths: dict[str, int] = {}

    for row in rows:
        record_id = int(row["id"])
        stored_path = row["stored_path"]
        if stored_path in seen_paths:
            issues.append(
                IntegrityIssue(
                    record_id=record_id,
                    severity="ERROR",
                    message="Duplicate stored path",
                    path=stored_path,
                )
            )
        else:
            seen_paths[stored_path] = record_id

        original = PROJECT_ROOT / stored_path
        original_hash = _check_original(row, original, issues)
        _check_metadata(row, original_hash, issues)

    failed = len(issues)
    passed = max(len(rows) - len({issue.record_id for issue in issues}), 0)
    return {
        "month": month,
        "records": len(rows),
        "passed": passed,
        "failed": failed,
        "status": "HEALTHY" if failed == 0 else "CORRUPTED",
        "issues": [issue.__dict__ for issue in issues],
    }


def _check_original(row: Any, original: Path, issues: list[IntegrityIssue]) -> str | None:
    record_id = int(row["id"])
    stored_path = row["stored_path"]
    if not original.exists() or not original.is_file():
        issues.append(
            IntegrityIssue(
                record_id=record_id,
                severity="ERROR",
                message="Original file missing",
                path=stored_path,
            )
        )
        return None

    original_hash = sha256_file(original)
    if original_hash != row["sha256"]:
        issues.append(
            IntegrityIssue(
                record_id=record_id,
                severity="ERROR",
                message="Original file modified",
                path=stored_path,
            )
        )
    return original_hash


def _check_metadata(row: Any, original_hash: str | None, issues: list[IntegrityIssue]) -> None:
    record_id = int(row["id"])
    metadata_path = row["metadata_path"]
    metadata_file = PROJECT_ROOT / metadata_path
    if not metadata_file.exists() or not metadata_file.is_file():
        issues.append(
            IntegrityIssue(
                record_id=record_id,
                severity="ERROR",
                message="Metadata file missing",
                path=metadata_path,
            )
        )
        return

    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        issues.append(
            IntegrityIssue(
                record_id=record_id,
                severity="ERROR",
                message="Metadata JSON invalid",
                path=metadata_path,
            )
        )
        return

    expected = {
        "record_date": row["record_date"],
        "direction": row["direction"],
        "original_filename": row["original_filename"],
        "stored_path": row["stored_path"],
        "sha256": row["sha256"],
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            issues.append(
                IntegrityIssue(
                    record_id=record_id,
                    severity="ERROR",
                    message=f"Metadata {key} mismatch",
                    path=metadata_path,
                )
            )

    if original_hash is not None and metadata.get("sha256") != original_hash:
        issues.append(
            IntegrityIssue(
                record_id=record_id,
                severity="ERROR",
                message="Metadata SHA256 does not match original",
                path=metadata_path,
            )
        )


def _validate_month(month: str) -> None:
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("month must be in YYYY-MM format") from exc
