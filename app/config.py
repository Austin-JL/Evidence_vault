from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ORIGINALS_DIR = DATA_DIR / "originals"
METADATA_DIR = DATA_DIR / "metadata"
REPORTS_DIR = DATA_DIR / "reports"
ARCHIVES_DIR = DATA_DIR / "archives"
TRASH_DIR = DATA_DIR / "trash"
DB_PATH = DATA_DIR / "evidence.db"
MODE_PATH = DATA_DIR / "mode.json"

VALID_DIRECTIONS = {"in", "out"}


def ensure_data_dirs() -> None:
    for path in (ORIGINALS_DIR, METADATA_DIR, REPORTS_DIR, ARCHIVES_DIR, TRASH_DIR):
        path.mkdir(parents=True, exist_ok=True)
