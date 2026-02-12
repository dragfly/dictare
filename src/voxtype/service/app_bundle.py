"""macOS .app bundle wrapper for voxtype.

Creates a lightweight .app bundle in /Applications so that macOS shows
"Voxtype" with its icon in Accessibility / Input Monitoring settings,
instead of a raw Python binary.
"""

from __future__ import annotations

import importlib.resources
import plistlib
import shutil
import stat
from pathlib import Path

APP_NAME = "Voxtype"
BUNDLE_ID = "com.dragfly.voxtype"


def get_app_path() -> Path:
    """Return the .app bundle path."""
    return Path("/Applications") / f"{APP_NAME}.app"


def get_executable_path() -> str:
    """Return the path to the executable inside the .app bundle."""
    return str(get_app_path() / "Contents" / "MacOS" / APP_NAME)


def create_app_bundle(python_path: str | None = None) -> Path:
    """Create the Voxtype.app bundle in /Applications.

    Args:
        python_path: Path to the Python interpreter. Defaults to sys.executable.

    Returns:
        Path to the created .app bundle.
    """
    import sys

    if python_path is None:
        python_path = sys.executable

    app_path = get_app_path()
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"

    # Clean up any existing bundle
    if app_path.exists():
        shutil.rmtree(app_path)

    # Create directory structure
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)

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
    }
    plist_path = contents / "Info.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump(info_plist, f)

    # Write launcher script
    launcher_path = macos_dir / APP_NAME
    launcher_path.write_text(
        f"#!/bin/bash\nexec {python_path} -m voxtype engine start -d --agents\n"
    )
    launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IEXEC)

    # Copy icns icon
    _copy_icns(resources_dir / f"{APP_NAME}.icns")

    return app_path


def remove_app_bundle() -> None:
    """Remove the Voxtype.app bundle from /Applications."""
    app_path = get_app_path()
    if app_path.exists():
        shutil.rmtree(app_path)


def _get_version() -> str:
    """Get voxtype version string."""
    try:
        from voxtype import __version__

        return __version__
    except Exception:
        return "0.0.0"


def _copy_icns(dest: Path) -> None:
    """Copy the Voxtype.icns from package resources to dest."""
    try:
        ref = importlib.resources.files("voxtype.resources") / "Voxtype.icns"
        with importlib.resources.as_file(ref) as icns_path:
            shutil.copy2(icns_path, dest)
    except Exception:
        # No icon available — .app will work without it
        pass
