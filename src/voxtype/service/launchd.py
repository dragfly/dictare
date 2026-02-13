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
    """Generate the LaunchAgent plist XML for the given python executable.

    If a .app bundle exists, ProgramArguments points to its executable
    so macOS associates permissions with the bundle (shows in Accessibility).
    Otherwise falls back to the raw python path.
    """
    from voxtype.service.app_bundle import get_app_path, get_executable_path

    app_path = get_app_path()
    if app_path.exists():
        program_args = [get_executable_path()]
    else:
        program_args = [python_path, "-m", "voxtype", "engine", "start", "-d", "--agents"]

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    plist: dict = {
        "Label": LABEL,
        "ProgramArguments": program_args,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_DIR / "stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "stderr.log"),
    }
    return plistlib.dumps(plist).decode()


def install() -> None:
    """Create .app bundle, write plist, and load the LaunchAgent."""
    import sys

    from voxtype.service.app_bundle import create_app_bundle

    create_app_bundle(sys.executable)
    plist_path = get_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(generate_plist(sys.executable))
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)


def uninstall() -> None:
    """Unload and remove the LaunchAgent, then remove .app bundle."""
    from voxtype.service.app_bundle import remove_app_bundle

    plist_path = get_plist_path()
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink(missing_ok=True)
    remove_app_bundle()


def is_installed() -> bool:
    """Check whether the plist file exists."""
    return get_plist_path().exists()


def is_loaded() -> bool:
    """Check whether the LaunchAgent is currently loaded in launchd."""
    result = subprocess.run(
        ["launchctl", "list", LABEL],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def start() -> None:
    """Load the LaunchAgent (starts the process and enables KeepAlive)."""
    plist_path = get_plist_path()
    if not plist_path.exists():
        raise RuntimeError("Service not installed. Run 'voxtype service install' first.")
    if is_loaded():
        return  # Already loaded
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)


def stop() -> None:
    """Unload the LaunchAgent (stops the process and disables KeepAlive)."""
    plist_path = get_plist_path()
    if not is_loaded():
        return  # Already unloaded
    subprocess.run(["launchctl", "unload", str(plist_path)], check=True)
