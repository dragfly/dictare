"""macOS .app bundle wrapper for dictare.

Creates a lightweight .app bundle so that macOS shows "Dictare" with its
icon in Accessibility / Input Monitoring settings, mic indicator, and
Activity Monitor — instead of "Python".

The bundle contains a compiled Swift launcher that:
1. Requests Microphone permission (shows "Dictare" in dialog)
2. Spawns the Python engine as a child process
3. Forwards signals for clean shutdown
"""

from __future__ import annotations

import importlib.resources
import logging
import plistlib
import shutil
import stat
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "Dictare"
BUNDLE_ID = "com.dragfly.dictare"


def get_app_path() -> Path:
    """Return the .app bundle path (~/Applications)."""
    return Path.home() / "Applications" / f"{APP_NAME}.app"


def get_executable_path() -> str:
    """Return the path to the executable inside the .app bundle."""
    return str(get_app_path() / "Contents" / "MacOS" / APP_NAME)


def create_app_bundle(
    python_path: str | None = None,
    app_dir: Path | None = None,
) -> Path:
    """Create the Dictare.app bundle.

    Args:
        python_path: Path to the Python interpreter. Defaults to sys.executable.
        app_dir: Directory to create the .app in. Defaults to ~/Applications.
                 Homebrew passes prefix (Cellar) to avoid sandbox restrictions.

    Returns:
        Path to the created .app bundle.
    """
    import sys

    if python_path is None:
        python_path = sys.executable

    if app_dir is not None:
        app_path = app_dir / f"{APP_NAME}.app"
    else:
        app_path = get_app_path()
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"

    # Skip recreation if the bundle already exists with same Python path AND
    # same launcher source.  Recreating the binary invalidates macOS TCC trust
    # (Accessibility / Input Monitoring), forcing re-grant.
    launcher_hash = _get_launcher_source_hash()
    if app_path.exists():
        existing_python_file = macos_dir / "python_path"
        existing_launcher = macos_dir / APP_NAME
        existing_hash_file = macos_dir / "launcher_hash"
        if existing_launcher.exists():
            same_python = (
                existing_python_file.exists()
                and existing_python_file.read_text().strip() == python_path
            )
            same_launcher = (
                existing_hash_file.exists()
                and existing_hash_file.read_text().strip() == launcher_hash
            )
            if same_python and same_launcher:
                logger.debug("App bundle already up to date, skipping recreation")
                return app_path
            if same_launcher and not same_python:
                # Only python_path changed — update without recompiling
                existing_python_file.write_text(python_path)
                logger.debug("Updated python_path in existing bundle")
                return app_path
            # Launcher source changed — must rebuild (TCC re-grant needed)
            logger.info("Launcher source changed — rebuilding app bundle")

        # Bundle needs update — remove it first.
        # Use subprocess rm -rf because shutil.rmtree fails on macOS when the
        # bundle has been launched (code signing / app translocation protection).
        subprocess.run(
            ["rm", "-rf", str(app_path)],
            check=False, capture_output=True,
        )

    # Create directory structure
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    # Write Info.plist
    info_plist = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": _get_version(),
        "CFBundleShortVersionString": _get_version(),
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": APP_NAME,
        "CFBundleIconFile": APP_NAME,
        "LSUIElement": True,  # No Dock icon
        "NSMicrophoneUsageDescription": "Dictare needs microphone access for voice-to-text.",
        "NSInputMonitoringUsageDescription": "Dictare uses Input Monitoring to detect the global Right ⌘ hotkey.",
    }
    plist_path = contents / "Info.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump(info_plist, f)

    # Write python_path config file (read by the native launcher)
    (macos_dir / "python_path").write_text(python_path)

    # Build native launcher (Swift → compiled binary).
    # Falls back to bash wrapper if swiftc is not available.
    launcher_path = macos_dir / APP_NAME
    if not _build_native_launcher(launcher_path):
        _write_bash_launcher(launcher_path, python_path)

    # Store launcher source hash for skip-if-unchanged logic
    (macos_dir / "launcher_hash").write_text(launcher_hash)

    # Copy icns icon
    _copy_icns(resources_dir / f"{APP_NAME}.icns")

    return app_path


def remove_app_bundle() -> None:
    """Remove the Dictare.app bundle."""
    for path in [get_app_path(), Path("/Applications") / f"{APP_NAME}.app"]:
        if path.exists():
            subprocess.run(["rm", "-rf", str(path)], check=False, capture_output=True)


def _build_native_launcher(dest: Path) -> bool:
    """Compile the Swift launcher binary.

    Returns True if compilation succeeded, False otherwise.
    """
    try:
        swift_src = importlib.resources.files("dictare.resources") / "launcher.swift"
        with importlib.resources.as_file(swift_src) as src_path:
            result = subprocess.run(
                ["swiftc", "-O", "-o", str(dest), str(src_path)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                return True
            logger.warning("swiftc failed: %s", result.stderr)
    except FileNotFoundError:
        logger.warning("swiftc not found — using bash launcher fallback")
    except Exception as e:
        logger.warning("Failed to build native launcher: %s", e)
    return False


def _write_bash_launcher(dest: Path, python_path: str) -> None:
    """Write a bash launcher script (fallback when swiftc unavailable)."""
    launcher_script = (
        f"#!/bin/bash\n"
        f'{python_path} -m dictare serve &\n'
        f'CHILD=$!\n'
        f'trap "kill $CHILD 2>/dev/null" SIGTERM SIGINT\n'
        f'wait $CHILD\n'
    )
    dest.write_text(launcher_script)
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC)


def _get_launcher_source_hash() -> str:
    """Return a short hash of the launcher.swift source for change detection."""
    import hashlib

    try:
        swift_src = importlib.resources.files("dictare.resources") / "launcher.swift"
        with importlib.resources.as_file(swift_src) as src_path:
            data = src_path.read_bytes()
            return hashlib.sha256(data).hexdigest()[:16]
    except Exception:
        return "unknown"


def _get_version() -> str:
    """Get dictare version string."""
    try:
        from dictare import __version__

        return __version__
    except Exception:
        return "0.0.0"


def _copy_icns(dest: Path) -> None:
    """Copy the Dictare.icns from package resources to dest."""
    try:
        ref = importlib.resources.files("dictare.resources") / "Dictare.icns"
        with importlib.resources.as_file(ref) as icns_path:
            shutil.copy2(icns_path, dest)
    except Exception:
        # No icon available — .app will work without it
        pass
