from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import db
from app.config import PROJECT_ROOT, TRASH_DIR, ensure_data_dirs
from app.mode import require_edit_mode


def remove_record(record_id: int) -> dict[str, Any]:
    ensure_data_dirs()
    require_edit_mode()

    row = db.get_record(record_id)
    if row is None:
        raise ValueError(f"record not found: {record_id}")

    removed_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    trash_dir = TRASH_DIR / f"{removed_at.replace(':', '').replace('+', '_')}_id{record_id}"
    trash_dir.mkdir(parents=True, exist_ok=False)

    moved_files = []
    missing_files = []
    for column in ("stored_path", "metadata_path"):
        source = PROJECT_ROOT / row[column]
        if not source.exists():
            missing_files.append(row[column])
            continue
        target = _next_available_path(trash_dir / source.name)
        shutil.move(str(source), target)
        moved_files.append({"from": row[column], "to": _relative(target)})

    db.delete_record(record_id)

    audit = {
        "removed_at": removed_at,
        "record": {key: row[key] for key in row.keys()},
        "moved_files": moved_files,
        "missing_files": missing_files,
    }
    audit_path = trash_dir / "removed_record.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "id": record_id,
        "trash_dir": _relative(trash_dir),
        "moved_files": moved_files,
        "missing_files": missing_files,
    }


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError(f"could not find available trash path for {path}")


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT))
