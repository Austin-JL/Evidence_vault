from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app import db
from app.config import METADATA_DIR, ORIGINALS_DIR, PROJECT_ROOT, VALID_DIRECTIONS, ensure_data_dirs
from app.hashing import sha256_file
from app.metadata import extract_file_metadata, metadata_json


def import_evidence(
    source_file: Path,
    direction: str,
    record_date: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_data_dirs()
    source_file = source_file.expanduser().resolve()
    if not source_file.exists() or not source_file.is_file():
        raise ValueError(f"File does not exist: {source_file}")
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"direction must be one of: {', '.join(sorted(VALID_DIRECTIONS))}")

    file_hash = sha256_file(source_file)
    duplicates = db.find_by_sha256(file_hash)
    if duplicates:
        first = duplicates[0]
        raise ValueError(
            "Duplicate import: same SHA256 already exists as "
            f"{first['stored_path']} on {first['record_date']} {first['direction']}"
        )

    extracted = extract_file_metadata(source_file)
    resolved_date = _normalize_record_date(record_date) or _date_from_capture(extracted.get("captured_at"))
    if resolved_date is None:
        raise ValueError("No --date provided and no EXIF capture date found")

    suffix = source_file.suffix or ".bin"
    target_original = _next_available_path(ORIGINALS_DIR, resolved_date, direction, suffix)
    target_metadata = _metadata_path_for(target_original, resolved_date)
    target_original.parent.mkdir(parents=True, exist_ok=True)
    target_metadata.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source_file, target_original)
    imported_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    metadata = metadata_json(
        record_date=resolved_date,
        direction=direction,
        original_filename=source_file.name,
        stored_path=_relative(target_original),
        file_hash=file_hash,
        imported_at=imported_at,
        extracted=extracted,
        note=note,
    )
    target_metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    record = {
        "record_date": resolved_date,
        "direction": direction,
        "original_filename": source_file.name,
        "stored_path": _relative(target_original),
        "metadata_path": _relative(target_metadata),
        "sha256": file_hash,
        "captured_at": extracted.get("captured_at"),
        "imported_at": imported_at,
        "gps_lat": extracted.get("gps_lat"),
        "gps_lng": extracted.get("gps_lng"),
        "device_model": extracted.get("device_model"),
        "file_size": extracted.get("file_size"),
        "mime_type": extracted.get("mime_type"),
        "note": note,
    }
    record_id = db.insert_record(record)
    return {**record, "id": record_id}


def _date_from_capture(captured_at: str | None) -> str | None:
    if not captured_at:
        return None
    try:
        return datetime.fromisoformat(captured_at).date().isoformat()
    except ValueError:
        return captured_at[:10] if len(captured_at) >= 10 else None


def _normalize_record_date(record_date: str | None) -> str | None:
    if record_date is None:
        return None

    value = record_date.strip()
    try:
        if len(value) == 8 and value.isdigit():
            return datetime.strptime(value, "%Y%m%d").date().isoformat()
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("date must be in YYYY-MM-DD or YYYYMMDD format") from exc


def _next_available_path(base: Path, record_date: str, direction: str, suffix: str) -> Path:
    year, month, day = record_date.split("-")
    day_dir = base / year / month / day
    candidate = day_dir / f"{direction}{suffix}"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = day_dir / f"{direction}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _metadata_path_for(original_path: Path, record_date: str) -> Path:
    year, month, day = record_date.split("-")
    return METADATA_DIR / year / month / day / f"{original_path.stem}.json"


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT))
