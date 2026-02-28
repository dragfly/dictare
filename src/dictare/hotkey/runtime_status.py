"""Helpers for hotkey runtime status persisted by the serve process."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def get_runtime_status_path() -> Path:
    return Path.home() / ".dictare" / "hotkey_runtime_status"

def read_runtime_status() -> dict[str, Any] | None:
    path = get_runtime_status_path()
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return data

def write_runtime_status(payload: dict[str, Any]) -> None:
    path = get_runtime_status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")))

def clear_runtime_status() -> None:
    get_runtime_status_path().unlink(missing_ok=True)
