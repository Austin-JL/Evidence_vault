from __future__ import annotations

from typing import Any

from app.archive import export_monthly_archive
from app.config import ARCHIVES_DIR
from app.integrity import check_month
from app.report import generate_monthly_report


def housekeep_month(month: str) -> dict[str, Any]:
    integrity = check_month(month)
    if integrity["failed"]:
        return {
            "month": month,
            "status": "ABORTED",
            "integrity": integrity,
            "report_path": None,
            "archive_path": None,
            "manifest_path": None,
            "manifest_sha256_path": None,
        }

    report_path = generate_monthly_report(month)
    archive_path = export_monthly_archive(month)
    return {
        "month": month,
        "status": "COMPLETE",
        "integrity": integrity,
        "report_path": str(report_path),
        "archive_path": str(archive_path),
        "manifest_path": str(ARCHIVES_DIR / f"{month}-manifest.json"),
        "manifest_sha256_path": str(ARCHIVES_DIR / f"{month}-manifest.sha256"),
    }
