from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.audit import append_audit_event, list_operations, log_operation
from app import db
from app.archive import export_monthly_archive
from app.housekeeping import housekeep_month
from app.importer import import_evidence
from app.integrity import check_month
from app.mode import enter_edit_mode, enter_view_mode, lock_edit_mode, require_edit_mode, set_passcode, status
from app.refresher import refresh_record_metadata
from app.remover import remove_record
from app.report import generate_monthly_report


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "import":
            require_edit_mode()
            precheck = check_month(_current_month())
            append_audit_event(
                event_type="INTEGRITY_CHECK",
                month=precheck["month"],
                details={"trigger": "pre_import", **_integrity_summary(precheck)},
            )
            if precheck["failed"]:
                raise ValueError("current month integrity check failed; import aborted")
            result = import_evidence(
                Path(args.file),
                args.direction,
                record_date=args.date,
                note=args.note,
            )
            print(f"Imported #{result['id']}: {result['stored_path']}")
            print(f"SHA256: {result['sha256']}")
            log_operation(
                action="import",
                status="success",
                target_type="record",
                target_id=result["id"],
                details=_details(args, result=result),
            )
            append_audit_event(
                event_type="IMPORT",
                record_id=result["id"],
                month=result["record_date"][:7],
                details={"stored_path": result["stored_path"], "sha256": result["sha256"]},
            )
            lock_edit_mode()
            return 0
        if args.command == "list":
            rows = db.list_month(args.month)
            print_records(rows)
            log_operation(
                action="list",
                status="success",
                details=_details(args, row_count=len(rows)),
            )
            return 0
        if args.command == "report":
            path = generate_monthly_report(args.month)
            print(f"Report written: {path}")
            log_operation(
                action="report",
                status="success",
                details=_details(args, output_path=str(path)),
            )
            return 0
        if args.command == "archive":
            path = export_monthly_archive(args.month)
            print(f"Archive written: {path}")
            log_operation(
                action="archive",
                status="success",
                details=_details(args, output_path=str(path)),
            )
            append_audit_event(
                event_type="ARCHIVE_CREATED",
                month=args.month,
                details={"output_path": str(path)},
            )
            return 0
        if args.command == "integrity-check":
            result = check_month(args.month)
            print_integrity_result(result)
            log_operation(
                action="integrity-check",
                status="success" if result["failed"] == 0 else "failed",
                details=_details(args, result=_integrity_summary(result)),
            )
            append_audit_event(
                event_type="INTEGRITY_CHECK",
                month=args.month,
                details={"trigger": "manual", **_integrity_summary(result)},
            )
            return 0 if result["failed"] == 0 else 1
        if args.command == "housekeep":
            result = housekeep_month(args.month)
            print_housekeep_result(result)
            log_operation(
                action="housekeep",
                status="success" if result["status"] == "COMPLETE" else "failed",
                details=_details(args, result=result),
            )
            append_audit_event(
                event_type="HOUSEKEEP",
                month=args.month,
                details=result,
            )
            if result["archive_path"]:
                append_audit_event(
                    event_type="ARCHIVE_CREATED",
                    month=args.month,
                    details={"output_path": result["archive_path"], "trigger": "housekeep"},
                )
            return 0 if result["status"] == "COMPLETE" else 1
        if args.command == "remove":
            row = db.get_record(args.id)
            if row is None:
                raise ValueError(f"record not found: {args.id}")
            if not args.yes:
                print_record_detail(row)
                confirmation = input("Type DELETE to remove this record from active evidence: ")
                if confirmation != "DELETE":
                    print("Canceled.")
                    log_operation(
                        action="remove",
                        status="canceled",
                        target_type="record",
                        target_id=args.id,
                        details=_details(args, reason="confirmation_mismatch"),
                    )
                    return 1
            result = remove_record(args.id)
            print(f"Removed record #{result['id']}")
            print(f"Trash: {result['trash_dir']}")
            for item in result["moved_files"]:
                print(f"Moved: {item['from']} -> {item['to']}")
            for path in result["missing_files"]:
                print(f"Missing file: {path}")
            log_operation(
                action="remove",
                status="success",
                target_type="record",
                target_id=args.id,
                details=_details(args, result=result),
            )
            append_audit_event(
                event_type="DELETE",
                record_id=args.id,
                month=row["record_date"][:7],
                details=result,
            )
            lock_edit_mode()
            return 0
        if args.command == "refresh-metadata":
            result = refresh_record_metadata(args.id)
            print(f"Refreshed metadata for record #{result['id']}")
            print(f"Captured: {result['captured_at'] or 'N/A'}")
            print(f"GPS: {_format_gps(result['gps_lat'], result['gps_lng'])}")
            print(f"Media: {_media_label(result['mime_type'])}")
            print(f"Metadata: {result['metadata_path']}")
            log_operation(
                action="refresh-metadata",
                status="success",
                target_type="record",
                target_id=args.id,
                details=_details(args, result=result),
            )
            lock_edit_mode()
            return 0
        if args.command == "mode":
            result = handle_mode(args)
            log_operation(
                action=f"mode:{args.mode_command}",
                status="success",
                details=_details(args),
            )
            return result
        if args.command == "audit":
            rows = list_operations(limit=args.limit, action=args.action, status=args.status)
            print_operations(rows)
            log_operation(
                action="audit",
                status="success",
                details=_details(args, row_count=len(rows)),
            )
            return 0
    except ValueError as exc:
        if hasattr(args, "command"):
            log_operation(
                action=_action_name(args),
                status="failed",
                target_type="record" if getattr(args, "id", None) is not None else None,
                target_id=getattr(args, "id", None),
                details=_details(args, error=str(exc)),
            )
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-vault")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="Import one evidence media file")
    import_parser.add_argument("--file", required=True, help="Photo, video, or Live Photo still image path")
    import_parser.add_argument("--direction", choices=("in", "out"), required=True)
    import_parser.add_argument("--date", help="Record date in YYYY-MM-DD or YYYYMMDD format")
    import_parser.add_argument("--note", help="Optional note stored in metadata and SQLite")

    list_parser = subparsers.add_parser("list", help="List records for a month")
    list_parser.add_argument("--month", required=True, help="Month in YYYY-MM format")

    report_parser = subparsers.add_parser("report", help="Generate monthly PDF report")
    report_parser.add_argument("--month", required=True, help="Month in YYYY-MM format")

    archive_parser = subparsers.add_parser("archive", help="Export monthly ZIP evidence package")
    archive_parser.add_argument("--month", required=True, help="Month in YYYY-MM format")

    integrity_parser = subparsers.add_parser("integrity-check", help="Verify monthly vault integrity")
    integrity_parser.add_argument("--month", required=True, help="Month in YYYY-MM format")

    housekeep_parser = subparsers.add_parser("housekeep", help="Run monthly integrity, report, manifest, and archive")
    housekeep_parser.add_argument("--month", required=True, help="Month in YYYY-MM format")

    remove_parser = subparsers.add_parser("remove", help="Remove one active evidence record")
    remove_parser.add_argument("--id", type=int, required=True, help="Record ID to remove")
    remove_parser.add_argument("--yes", action="store_true", help="Skip interactive DELETE confirmation")

    refresh_parser = subparsers.add_parser("refresh-metadata", help="Re-extract metadata for one record")
    refresh_parser.add_argument("--id", type=int, required=True, help="Record ID to refresh")

    mode_parser = subparsers.add_parser("mode", help="Show or change edit/view mode")
    mode_subparsers = mode_parser.add_subparsers(dest="mode_command", required=True)
    mode_subparsers.add_parser("status", help="Show current mode")
    mode_subparsers.add_parser("set-passcode", help="Set or replace the edit-mode passcode")
    mode_subparsers.add_parser("edit", help="Unlock edit mode with passcode")
    mode_subparsers.add_parser("view", help="Lock into view mode")

    audit_parser = subparsers.add_parser("audit", help="Show operation log")
    audit_parser.add_argument("--limit", type=int, default=50, help="Maximum rows to show")
    audit_parser.add_argument("--action", help="Filter by action, such as import or remove")
    audit_parser.add_argument("--status", help="Filter by status, such as success or failed")

    return parser


def print_records(rows) -> None:
    if not rows:
        print("No records found.")
        return
    for row in rows:
        gps = "N/A"
        if row["gps_lat"] is not None and row["gps_lng"] is not None:
            gps = f"{row['gps_lat']:.6f}, {row['gps_lng']:.6f}"
        print(
            f"#{row['id']} {row['record_date']} {row['direction'].upper():3} "
            f"{row['captured_at'] or 'N/A'} "
            f"{gps} "
            f"{row['sha256'][:12]}... "
            f"{_media_label(row['mime_type'])} "
            f"{row['stored_path']}"
        )


def print_record_detail(row) -> None:
    gps = "N/A"
    if row["gps_lat"] is not None and row["gps_lng"] is not None:
        gps = f"{row['gps_lat']:.6f}, {row['gps_lng']:.6f}"
    print(f"ID: {row['id']}")
    print(f"Date: {row['record_date']}")
    print(f"Direction: {row['direction']}")
    print(f"Captured: {row['captured_at'] or 'N/A'}")
    print(f"GPS: {gps}")
    print(f"SHA256: {row['sha256']}")
    print(f"Media: {_media_label(row['mime_type'])}")
    print(f"Original: {row['stored_path']}")
    print(f"Metadata: {row['metadata_path']}")


def print_integrity_result(result: dict) -> None:
    print("Integrity Check")
    print()
    print("Month:")
    print(result["month"])
    print()
    print("Records:")
    print(result["records"])
    print()
    print("Passed:")
    print(result["passed"])
    print()
    print("Failed:")
    print(result["failed"])
    if result["issues"]:
        print()
        print("Issues:")
        for issue in result["issues"]:
            path = f" path={issue['path']}" if issue.get("path") else ""
            print(f"{issue['severity']} record={issue['record_id']} {issue['message']}{path}")
    print()
    print("Vault Status:")
    print(result["status"])


def print_housekeep_result(result: dict) -> None:
    print("Housekeeping")
    print()
    print("Month:")
    print(result["month"])
    print()
    print("Status:")
    print(result["status"])
    print()
    print("Vault Status:")
    print(result["integrity"]["status"])
    if result["status"] != "COMPLETE":
        print()
        print("Aborted before report/archive generation.")
        return
    print()
    print(f"Report: {result['report_path']}")
    print(f"Archive: {result['archive_path']}")
    print(f"Manifest: {result['manifest_path']}")
    print(f"Manifest SHA256: {result['manifest_sha256_path']}")


def print_operations(rows) -> None:
    if not rows:
        print("No operations found.")
        return
    for row in rows:
        target = ""
        if row["target_type"] or row["target_id"]:
            target = f" {row['target_type'] or ''}:{row['target_id'] or ''}".strip()
        details = json.loads(row["details_json"])
        summary = _operation_summary(details)
        print(
            f"#{row['id']} {row['occurred_at']} {row['actor']} "
            f"{row['action']} {row['status']} {target} {summary}".rstrip()
        )


def handle_mode(args) -> int:
    if args.mode_command == "status":
        current = status()
        configured = "yes" if current["configured"] else "no"
        print(f"Mode: {current['mode']}")
        print(f"Passcode configured: {configured}")
        if current.get("edit_expires_at"):
            print(f"Edit expires at: {current['edit_expires_at']}")
        return 0
    if args.mode_command == "set-passcode":
        passcode = getpass.getpass("New passcode: ")
        confirm = getpass.getpass("Confirm passcode: ")
        if passcode != confirm:
            raise ValueError("passcodes do not match")
        set_passcode(passcode)
        print("Passcode set. Mode: view")
        return 0
    if args.mode_command == "edit":
        passcode = getpass.getpass("Passcode: ")
        enter_edit_mode(passcode)
        current = status()
        print("Mode: edit")
        print(f"Edit expires at: {current['edit_expires_at']}")
        return 0
    if args.mode_command == "view":
        enter_view_mode()
        print("Mode: view")
        return 0
    raise ValueError(f"unknown mode command: {args.mode_command}")


def _action_name(args) -> str:
    if args.command == "mode":
        return f"mode:{getattr(args, 'mode_command', 'unknown')}"
    return args.command


def _details(args, **extra) -> dict:
    details = {
        key: value
        for key, value in vars(args).items()
        if key not in {"mode_command"} and value is not None
    }
    details.update(extra)
    return details


def _operation_summary(details: dict) -> str:
    parts = []
    for key in ("month", "file", "direction", "date", "id", "row_count", "output_path", "archive_path", "error"):
        if key in details:
            parts.append(f"{key}={details[key]}")
    return " ".join(parts)


def _integrity_summary(result: dict) -> dict:
    return {
        "month": result["month"],
        "records": result["records"],
        "passed": result["passed"],
        "failed": result["failed"],
        "status": result["status"],
    }


def _current_month() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m")


def _format_gps(lat: float | None, lng: float | None) -> str:
    if lat is None or lng is None:
        return "N/A"
    return f"{lat:.6f}, {lng:.6f}"


def _media_label(mime_type: str | None) -> str:
    if not mime_type or "/" not in mime_type:
        return "file"
    return mime_type.split("/", 1)[0]


if __name__ == "__main__":
    raise SystemExit(main())
