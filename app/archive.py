from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.config import ARCHIVES_DIR, PROJECT_ROOT, ensure_data_dirs
from app.report import generate_monthly_report


def export_monthly_archive(month: str) -> Path:
    ensure_data_dirs()
    rows = db.list_month(month)
    report_path = generate_monthly_report(month)
    archive_path = ARCHIVES_DIR / f"{month}.zip"

    manifest = {
        "month": month,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "total_records": len(rows),
        "records": [_manifest_record(row) for row in rows],
    }

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for row in rows:
            stored = PROJECT_ROOT / row["stored_path"]
            metadata = PROJECT_ROOT / row["metadata_path"]
            if stored.exists():
                zip_file.write(stored, Path("originals") / stored.name)
            if metadata.exists():
                zip_file.write(metadata, Path("metadata") / metadata.name)
        zip_file.write(report_path, report_path.name)
        zip_file.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    return archive_path


def _manifest_record(row) -> dict:
    return {
        "id": row["id"],
        "record_date": row["record_date"],
        "direction": row["direction"],
        "stored_path": row["stored_path"],
        "metadata_path": row["metadata_path"],
        "sha256": row["sha256"],
        "captured_at": row["captured_at"],
        "gps": {"lat": row["gps_lat"], "lng": row["gps_lng"]},
        "file_size": row["file_size"],
        "mime_type": row["mime_type"],
        "media_type": _media_type(row["mime_type"]),
        "note": row["note"],
    }


def _media_type(mime_type: str | None) -> str:
    if not mime_type or "/" not in mime_type:
        return "unknown"
    return mime_type.split("/", 1)[0]
