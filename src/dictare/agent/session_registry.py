"""Best-effort per-folder registry binding session names to agent profiles.

Dictare is a light abstraction over heterogeneous agent CLIs: the registry
remembers which profile a named session was launched with in a given folder,
so ``dictare agent <name> --continue`` can pick the right agent type without
the user remembering it. It is a POINTER, never the source of truth — the
agent's own session store is. Every operation is best-effort: a corrupt or
missing registry must never break launching an agent.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REGISTRY_DIR = Path.home() / ".dictare" / "projects"


def _encode_cwd(cwd: str) -> str:
    """Encode a folder path into a flat filename (Claude-projects style)."""
    return cwd.replace(os.sep, "-")


def _registry_path(cwd: str) -> Path:
    return REGISTRY_DIR / f"{_encode_cwd(cwd)}.json"


def load_registry(cwd: str) -> dict[str, dict[str, Any]]:
    """Load the registry for a folder. Returns {} on any problem."""
    path = _registry_path(cwd)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(v, dict)}
    except FileNotFoundError:
        pass
    except Exception:
        logger.debug("Unreadable session registry: %s", path, exc_info=True)
    return {}


def lookup(cwd: str, name: str) -> dict[str, Any] | None:
    """Return the registry entry for (folder, name), or None."""
    return load_registry(cwd).get(name)


def record_launch(cwd: str, name: str, profile: str) -> None:
    """Record that session *name* was launched with *profile* in *cwd*.

    Best-effort: failures are logged at debug level and never raised.
    """
    try:
        registry = load_registry(cwd)
        entry = registry.get(name, {})
        registry[name] = {
            "profile": profile,
            "last_used": datetime.now(UTC).isoformat(timespec="seconds"),
            "launches": int(entry.get("launches", 0)) + 1,
        }
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        path = _registry_path(cwd)
        # Atomic write: a crash mid-write must not corrupt the registry.
        fd, tmp = tempfile.mkstemp(dir=str(REGISTRY_DIR), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2, sort_keys=True)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    except Exception:
        logger.debug("Could not record session launch", exc_info=True)


def list_entries(cwd: str) -> list[tuple[str, dict[str, Any]]]:
    """Return (name, entry) pairs for a folder, most recently used first."""
    registry = load_registry(cwd)
    return sorted(
        registry.items(),
        key=lambda item: str(item[1].get("last_used", "")),
        reverse=True,
    )
