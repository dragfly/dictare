"""Standard paths for dictare data directory."""

from __future__ import annotations

from pathlib import Path


def get_dictare_dir() -> Path:
    """Get the dictare data directory (~/.dictare)."""
    return Path.home() / ".dictare"

def get_pid_path() -> Path:
    """Get the engine PID file path."""
    return get_dictare_dir() / "engine.pid"
