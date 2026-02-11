"""Standard paths for voxtype data directory."""

from __future__ import annotations

from pathlib import Path


def get_voxtype_dir() -> Path:
    """Get the voxtype data directory (~/.voxtype)."""
    return Path.home() / ".voxtype"


def get_pid_path() -> Path:
    """Get the engine PID file path."""
    return get_voxtype_dir() / "engine.pid"
