from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import MODE_PATH, ensure_data_dirs


EDIT_MODE_TTL_SECONDS = 300


def status() -> dict[str, Any]:
    state = _load_state()
    if state is None:
        return {"configured": False, "mode": "edit", "edit_expires_at": None}
    if state.get("mode") == "edit" and _is_expired(state.get("edit_expires_at")):
        state["mode"] = "view"
        state["edit_expires_at"] = None
        state["updated_at"] = _now()
        _save_state(state)
    return {
        "configured": True,
        "mode": state.get("mode", "view"),
        "edit_expires_at": state.get("edit_expires_at"),
    }


def set_passcode(passcode: str) -> None:
    _validate_passcode(passcode)
    salt = secrets.token_hex(16)
    _save_state(
        {
            "mode": "view",
            "edit_expires_at": None,
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
    state["edit_expires_at"] = _edit_expires_at()
    state["updated_at"] = _now()
    _save_state(state)


def enter_view_mode() -> None:
    state = _load_state()
    if state is None:
        return
    state["mode"] = "view"
    state["edit_expires_at"] = None
    state["updated_at"] = _now()
    _save_state(state)


def lock_edit_mode() -> None:
    enter_view_mode()


def require_edit_mode() -> None:
    state = _load_state()
    if state is None:
        return
    if state.get("mode") != "edit":
        raise ValueError("edit mode is locked; run `mode edit` with your passcode first")
    if _is_expired(state.get("edit_expires_at")):
        state["mode"] = "view"
        state["edit_expires_at"] = None
        state["updated_at"] = _now()
        _save_state(state)
        raise ValueError("edit mode expired; run `mode edit` with your passcode again")


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


def _edit_expires_at() -> str:
    return (datetime.now(timezone.utc).astimezone() + timedelta(seconds=EDIT_MODE_TTL_SECONDS)).isoformat(
        timespec="seconds"
    )


def _is_expired(value: str | None) -> bool:
    if not value:
        return True
    try:
        return datetime.now(timezone.utc).astimezone() >= datetime.fromisoformat(value)
    except ValueError:
        return True


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
