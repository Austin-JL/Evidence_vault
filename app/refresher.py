from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import db
from app.config import PROJECT_ROOT, ensure_data_dirs
from app.hashing import sha256_file
from app.metadata import extract_file_metadata, metadata_json
from app.mode import require_edit_mode


def refresh_record_metadata(record_id: int) -> dict[str, Any]:
    ensure_data_dirs()
    require_edit_mode()

    row = db.get_record(record_id)
    if row is None:
        raise ValueError(f"record not found: {record_id}")

    original_path = PROJECT_ROOT / row["stored_path"]
    if not original_path.exists() or not original_path.is_file():
        raise ValueError(f"stored file is missing: {row['stored_path']}")

    file_hash = sha256_file(original_path)
    if file_hash != row["sha256"]:
        raise ValueError(f"stored file hash mismatch for record {record_id}")

    extracted = extract_file_metadata(original_path)
    imported_at = row["imported_at"] or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    metadata = metadata_json(
        record_date=row["record_date"],
        direction=row["direction"],
        original_filename=row["original_filename"],
        stored_path=row["stored_path"],
        file_hash=row["sha256"],
        imported_at=imported_at,
        extracted=extracted,
        note=row["note"],
    )

    metadata_path = PROJECT_ROOT / row["metadata_path"]
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    updated = {
        "captured_at": extracted.get("captured_at"),
        "gps_lat": extracted.get("gps_lat"),
        "gps_lng": extracted.get("gps_lng"),
        "device_model": extracted.get("device_model"),
        "file_size": extracted.get("file_size"),
        "mime_type": extracted.get("mime_type"),
    }
    db.update_record_metadata(record_id, updated)
    return {**updated, "id": record_id, "metadata_path": row["metadata_path"]}
