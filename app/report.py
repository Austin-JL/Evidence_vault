from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.config import REPORTS_DIR, ensure_data_dirs


def generate_monthly_report(month: str) -> Path:
    ensure_data_dirs()
    rows = db.list_month(month)
    output = REPORTS_DIR / f"{month}.pdf"
    try:
        _generate_pdf_with_reportlab(month, rows, output)
    except ImportError:
        _generate_plain_pdf(month, rows, output)
    return output


def _generate_pdf_with_reportlab(month: str, rows: list, output: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    doc = SimpleDocTemplate(str(output), pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Evidence Vault Monthly Report", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Month: {month}", styles["Normal"]),
        Paragraph(f"Generated At: {_now()}", styles["Normal"]),
        Paragraph(f"Total Records: {len(rows)}", styles["Normal"]),
        PageBreak(),
    ]

    for date, day_rows in _group_by_date(rows).items():
        story.append(Paragraph(date, styles["Heading2"]))
        for row in day_rows:
            story.extend(_row_paragraphs(row, styles))
        story.append(Spacer(1, 10))

    doc.build(story)


def _row_paragraphs(row, styles) -> list:
    gps = "N/A"
    if row["gps_lat"] is not None and row["gps_lng"] is not None:
        gps = f"{row['gps_lat']:.6f}, {row['gps_lng']:.6f}"
    captured = _time_only(row["captured_at"])
    return [
        Paragraph(row["direction"].upper() + ":", styles["Heading3"]),
        Paragraph(f"Captured At: {captured}", styles["Normal"]),
        Paragraph(f"GPS: {gps}", styles["Normal"]),
        Paragraph(f"SHA256: {row['sha256']}", styles["Normal"]),
        Paragraph(f"Media: {_media_label(row['mime_type'])}", styles["Normal"]),
        Paragraph(f"File: {Path(row['stored_path']).name}", styles["Normal"]),
        Spacer(1, 8),
    ]


def _generate_plain_pdf(month: str, rows: list, output: Path) -> None:
    # Small valid text-only PDF fallback for environments without reportlab.
    lines = [
        "Evidence Vault Monthly Report",
        f"Month: {month}",
        f"Generated At: {_now()}",
        f"Total Records: {len(rows)}",
        "",
    ]
    for date, day_rows in _group_by_date(rows).items():
        lines.append(date)
        for row in day_rows:
            gps = "N/A"
            if row["gps_lat"] is not None and row["gps_lng"] is not None:
                gps = f"{row['gps_lat']:.6f}, {row['gps_lng']:.6f}"
            lines.extend(
                [
                    f"{row['direction'].upper()}:",
                    f"Captured At: {_time_only(row['captured_at'])}",
                    f"GPS: {gps}",
                    f"SHA256: {row['sha256']}",
                    f"Media: {_media_label(row['mime_type'])}",
                    f"File: {Path(row['stored_path']).name}",
                    "",
                ]
            )
    _write_simple_pdf(output, lines)


def _write_simple_pdf(output: Path, lines: list[str]) -> None:
    escaped = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in lines
    ]
    text = "BT /F1 10 Tf 50 790 Td 14 TL " + " T* ".join(f"({line}) Tj" for line in escaped) + " ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(text.encode('utf-8'))} >>\nstream\n{text}\nendstream".encode("utf-8"),
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode())
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_at = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    )
    output.write_bytes(bytes(content))


def _group_by_date(rows: list) -> dict[str, list]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["record_date"]].append(row)
    return dict(grouped)


def _time_only(value: str | None) -> str:
    if not value:
        return "N/A"
    try:
        return datetime.fromisoformat(value).time().isoformat(timespec="seconds")
    except ValueError:
        return value


def _media_label(mime_type: str | None) -> str:
    if not mime_type or "/" not in mime_type:
        return "file"
    return mime_type.split("/", 1)[0]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
