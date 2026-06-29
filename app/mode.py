from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from app.config import MODE_PATH, ensure_data_dirs


def status() -> dict[str, Any]:
    state = _load_state()
    if state is None:
        return {"configured": False, "mode": "edit"}
    return {"configured": True, "mode": state.get("mode", "view")}


def set_passcode(passcode: str) -> None:
    _validate_passcode(passcode)
    salt = secrets.token_hex(16)
    _save_state(
        {
            "mode": "view",
            "salt": salt,
            "passcode_hash": _hash_passcode(passcode, salt),
            "updated_at": _now(),
        }
    )


def enter_edit_mode(passcode: str) -> None:
    state = _require_state()
    if not _verify_passcode(passcode, state):
        raise ValueError("invalid passcode")
    state["mode"] = "edit"
    state["updated_at"] = _now()
    _save_state(state)


def enter_view_mode() -> None:
    state = _load_state()
    if state is None:
        return
    state["mode"] = "view"
    state["updated_at"] = _now()
    _save_state(state)


def require_edit_mode() -> None:
    state = _load_state()
    if state is None:
        return
    if state.get("mode") != "edit":
        raise ValueError("edit mode is locked; run `mode edit` with your passcode first")


def _load_state() -> dict[str, Any] | None:
    ensure_data_dirs()
    if not MODE_PATH.exists():
        return None
    return json.loads(MODE_PATH.read_text(encoding="utf-8"))


def _require_state() -> dict[str, Any]:
    state = _load_state()
    if state is None:
        raise ValueError("no passcode configured; run `mode set-passcode` first")
    return state


def _save_state(state: dict[str, Any]) -> None:
    ensure_data_dirs()
    MODE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_passcode(passcode: str) -> None:
    if len(passcode) < 6:
        raise ValueError("passcode must be at least 6 characters")


def _hash_passcode(passcode: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", passcode.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return digest.hex()


def _verify_passcode(passcode: str, state: dict[str, Any]) -> bool:
    expected = state.get("passcode_hash", "")
    actual = _hash_passcode(passcode, state.get("salt", ""))
    return hmac.compare_digest(actual, expected)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
