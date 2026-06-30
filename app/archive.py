from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import db
from app.audit import count_audit_events, list_audit_events
from app.config import ARCHIVES_DIR, PROJECT_ROOT, TRASH_DIR, ensure_data_dirs
from app.hashing import sha256_bytes, sha256_file
from app.report import generate_monthly_report

VAULT_VERSION = "1"


def export_monthly_archive(month: str) -> Path:
    ensure_data_dirs()
    rows = db.list_month(month)
    report_path = generate_monthly_report(month)
    manifest = build_monthly_manifest(month, rows)
    manifest_bytes = _manifest_bytes(manifest)
    manifest_hash = sha256_bytes(manifest_bytes)
    archive_path = ARCHIVES_DIR / f"{month}.zip"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        _write_records(zip_file, rows)
        _write_audit(zip_file, month)
        _write_trash(zip_file, month)
        zip_file.write(report_path, "report.pdf")
        zip_file.writestr("manifest.json", manifest_bytes)
        zip_file.writestr("manifest.sha256", f"{manifest_hash}  manifest.json\n")

    _write_manifest_files(month, manifest_bytes, manifest_hash)
    return archive_path


def build_monthly_manifest(month: str, rows: list[Any] | None = None) -> dict[str, Any]:
    ensure_data_dirs()
    rows = db.list_month(month) if rows is None else rows
    original_files = [_file_manifest(row["stored_path"]) for row in rows]
    metadata_files = [_file_manifest(row["metadata_path"]) for row in rows]
    trash_files = _trash_file_manifests(month)
    audit_events = list_audit_events(limit=None, month=month)
    return {
        "month": month,
        "generated_at": _now(),
        "vault_version": VAULT_VERSION,
        "total_records": len(rows),
        "total_audit_events": count_audit_events(month),
        "total_trash_items": len(trash_files),
        "original_files": original_files,
        "metadata_files": metadata_files,
        "trash_files": trash_files,
        "audit_events": [_audit_event_manifest(row) for row in reversed(audit_events)],
        "records": [_manifest_record(row) for row in rows],
    }


def _write_records(zip_file: zipfile.ZipFile, rows: list[Any]) -> None:
    for row in rows:
        for column in ("stored_path", "metadata_path"):
            path = PROJECT_ROOT / row[column]
            if path.exists():
                zip_file.write(path, _archive_name(path))


def _write_audit(zip_file: zipfile.ZipFile, month: str) -> None:
    events = [_audit_event_manifest(row) for row in reversed(list_audit_events(limit=None, month=month))]
    zip_file.writestr("audit/audit_events.json", json.dumps(events, ensure_ascii=False, indent=2) + "\n")


def _write_trash(zip_file: zipfile.ZipFile, month: str) -> None:
    for path in _trash_paths(month):
        if path.is_file():
            zip_file.write(path, _archive_name(path))


def _write_manifest_files(month: str, manifest_bytes: bytes, manifest_hash: str) -> None:
    manifest_path = ARCHIVES_DIR / f"{month}-manifest.json"
    checksum_path = ARCHIVES_DIR / f"{month}-manifest.sha256"
    manifest_path.write_bytes(manifest_bytes)
    checksum_path.write_text(f"{manifest_hash}  {manifest_path.name}\n", encoding="utf-8")


def _manifest_record(row: Any) -> dict[str, Any]:
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


def _file_manifest(relative_path: str) -> dict[str, Any]:
    path = PROJECT_ROOT / relative_path
    item: dict[str, Any] = {"path": relative_path, "exists": path.exists()}
    if path.exists() and path.is_file():
        item["sha256"] = sha256_file(path)
        item["size"] = path.stat().st_size
    return item


def _trash_file_manifests(month: str) -> list[dict[str, Any]]:
    return [_file_manifest(str(path.relative_to(PROJECT_ROOT))) for path in _trash_paths(month) if path.is_file()]


def _trash_paths(month: str) -> list[Path]:
    if not TRASH_DIR.exists():
        return []
    return sorted(path for path in TRASH_DIR.glob(f"{month}-*/*") if path.is_file())


def _audit_event_manifest(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "event_type": row["event_type"],
        "record_id": row["record_id"],
        "month": row["month"],
        "created_at": row["created_at"],
        "details": json.loads(row["details_json"]),
        "previous_hash": row["previous_hash"],
        "event_hash": row["event_hash"],
    }


def _archive_name(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT / "data"))


def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _media_type(mime_type: str | None) -> str:
    if not mime_type or "/" not in mime_type:
        return "unknown"
    return mime_type.split("/", 1)[0]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
