"""Engine state persistence across restarts.

Saves/loads runtime state (active agent, output mode, listening) to a
JSON file so the engine can restore its previous state after restart
or upgrade.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dictare.utils.paths import get_dictare_dir

logger = logging.getLogger(__name__)

STATE_FILE = "state.json"

def _state_path() -> Path:
    return get_dictare_dir() / STATE_FILE

def save_state(
    *,
    active_agent: str | None = None,
    output_mode: str = "keyboard",
    listening: bool = False,
) -> None:
    """Save engine state to disk."""
    path = _state_path()
    data = {
        "active_agent": active_agent,
        "output_mode": output_mode,
        "listening": listening,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
    except OSError as e:
        logger.warning("Failed to save state: %s", e)

def load_state() -> dict[str, Any]:
    """Load engine state from disk. Returns defaults if file missing/corrupt."""
    path = _state_path()
    defaults: dict[str, Any] = {
        "active_agent": None,
        "output_mode": "keyboard",
        "listening": False,
    }
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text())
        return {
            "active_agent": data.get("active_agent"),
            "output_mode": data.get("output_mode", "keyboard"),
            "listening": data.get("listening", False),
        }
    except (OSError, json.JSONDecodeError, KeyError) as e:
        logger.debug("Failed to load state: %s", e)
        return defaults

def clear_state() -> None:
    """Remove state file."""
    path = _state_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
