"""Engine session state persistence.

Saves/loads runtime state (active agent, output mode, listening) to a
JSON file so the engine can restore its previous state after restart.

Session expiry: if the last save was more than SESSION_TIMEOUT_S ago,
the state is considered stale and load_state() returns None, signalling
the caller to use config.toml defaults instead.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from dictare.utils.paths import get_dictare_dir

logger = logging.getLogger(__name__)

STATE_FILE = "session-state.json"
SESSION_TIMEOUT_S = 3600  # 60 minutes

def _state_path() -> Path:
    return get_dictare_dir() / STATE_FILE

def save_state(
    *,
    active_agent: str | None = None,
    output_mode: str = "keyboard",
    listening: bool = False,
) -> None:
    """Save engine state to disk with a timestamp."""
    path = _state_path()
    data = {
        "active_agent": active_agent,
        "output_mode": output_mode,
        "listening": listening,
        "last_active": time.time(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
    except OSError as e:
        logger.warning("Failed to save state: %s", e)

def load_state() -> dict[str, Any] | None:
    """Load engine state from disk.

    Returns:
        State dict if the session is fresh (< SESSION_TIMEOUT_S).
        None if the file is missing, corrupt, or the session expired.
        Callers should fall back to config.toml defaults when None.
    """
    path = _state_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Failed to load state: %s", e)
        return None

    # Check session expiry
    last_active = data.get("last_active", 0)
    elapsed = time.time() - last_active
    if elapsed > SESSION_TIMEOUT_S:
        logger.info(
            "Session expired (%.0f min ago > %d min limit), using config defaults",
            elapsed / 60, SESSION_TIMEOUT_S // 60,
        )
        return None

    logger.info("Session still fresh (%.0f s ago), restoring state", elapsed)
    return {
        "active_agent": data.get("active_agent"),
        "output_mode": data.get("output_mode"),
        "listening": data.get("listening", False),
    }

def clear_state() -> None:
    """Remove state file."""
    path = _state_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
