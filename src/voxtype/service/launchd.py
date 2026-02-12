"""macOS LaunchAgent management for voxtype."""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

LABEL = "com.dragfly.voxtype"
LOG_DIR = Path.home() / "Library" / "Logs" / "voxtype"

def get_plist_path() -> Path:
    """Return the LaunchAgent plist path."""
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"

def generate_plist(python_path: str) -> str:
    """Generate the LaunchAgent plist XML for the given python executable."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    plist: dict = {
        "Label": LABEL,
        "ProgramArguments": [python_path, "-m", "voxtype", "engine", "start", "-d", "--agents"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_DIR / "stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "stderr.log"),
    }
    return plistlib.dumps(plist).decode()

def install() -> None:
    """Write plist and load the LaunchAgent."""
    import sys

    plist_path = get_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(generate_plist(sys.executable))
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)

def uninstall() -> None:
    """Unload and remove the LaunchAgent."""
    plist_path = get_plist_path()
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink(missing_ok=True)

def is_installed() -> bool:
    """Check whether the plist file exists."""
    return get_plist_path().exists()

def start() -> None:
    """Start the LaunchAgent."""
    subprocess.run(["launchctl", "start", LABEL], check=True)

def stop() -> None:
    """Stop the LaunchAgent."""
    subprocess.run(["launchctl", "stop", LABEL], check=True)
