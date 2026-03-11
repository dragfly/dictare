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
BUNDLE_ID = "dev.dragfly.dictare"

def get_app_path() -> Path:
    """Return the .app bundle path (~/Applications)."""
    return Path.home() / "Applications" / f"{APP_NAME}.app"

def get_executable_path() -> str:
    """Return the path to the executable inside the .app bundle."""
    return str(get_app_path() / "Contents" / "MacOS" / APP_NAME)

def create_app_bundle(
    python_path: str | None = None,
    app_dir: Path | None = None,
    prebuilt_launcher: Path | None = None,
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

    # Always write python_path externally — the signed bundle must not be
    # modified (any change invalidates the code signature).
    _write_external_python_path(python_path)

    # Skip recreation if the bundle already exists with same launcher source.
    # Recreating the binary invalidates macOS TCC trust (Accessibility / Input
    # Monitoring), forcing re-grant.  Signed launchers (Developer ID) have
    # stable TCC via Team ID — even replacing the binary preserves permissions.
    launcher_hash = _get_launcher_source_hash()
    if app_path.exists():
        existing_launcher = macos_dir / APP_NAME
        # CI puts metadata in Resources/ (codesign requires MacOS/ to contain
        # only signed Mach-O binaries).  Local builds use MacOS/ (legacy).
        existing_hash_file = (
            resources_dir / "launcher_hash" if (resources_dir / "launcher_hash").exists()
            else macos_dir / "launcher_hash"
        )
        existing_signed = (
            resources_dir / "launcher_signed" if (resources_dir / "launcher_signed").exists()
            else macos_dir / "launcher_signed"
        )
        if existing_launcher.exists():
            same_launcher = (
                existing_hash_file.exists()
                and existing_hash_file.read_text().strip() == launcher_hash
            )
            # If prebuilt provided but current launcher isn't signed, don't skip —
            # we want to upgrade from ad-hoc to Developer ID signed.
            upgrade_to_signed = prebuilt_launcher and not existing_signed.exists()
            if same_launcher and not upgrade_to_signed:
                logger.debug("App bundle already up to date, skipping recreation")
                return app_path
            if existing_signed.exists() and not prebuilt_launcher:
                # Signed launcher installed, no new prebuilt provided —
                # keep existing signed binary, python_path is external.
                logger.debug("Keeping existing signed launcher")
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

    # Install launcher binary.
    # Priority: Cellar bundle → pre-built binary → compile from source → bash fallback.
    launcher_path = macos_dir / APP_NAME

    # Auto-detect signed bundle from Homebrew Cellar
    if not prebuilt_launcher:
        cellar_bundle = _find_cellar_bundle()
        if cellar_bundle:
            logger.info("Found signed bundle in Cellar: %s", cellar_bundle)
            _install_cellar_bundle(cellar_bundle, app_path)
            return app_path

    if prebuilt_launcher and _install_prebuilt_launcher(prebuilt_launcher, launcher_path):
        logger.info("Using pre-built signed launcher")
        (macos_dir / "launcher_signed").write_text("true")
    elif _build_native_launcher(launcher_path):
        (macos_dir / "launcher_signed").unlink(missing_ok=True)
    else:
        _write_bash_launcher(launcher_path, python_path)
        (macos_dir / "launcher_signed").unlink(missing_ok=True)

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

def _write_external_python_path(python_path: str) -> None:
    """Write python_path to ~/.dictare/python_path (external to the bundle).

    The Swift launcher reads from here first, so the signed .app bundle
    remains immutable — no code signature invalidation on brew upgrades.
    """
    config_dir = Path.home() / ".dictare"
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "python_path"
    # Remove first — macOS com.apple.provenance xattr on existing file
    # can cause EPERM when a different process tries to overwrite it.
    target.unlink(missing_ok=True)
    target.write_text(python_path)

def _find_cellar_bundle() -> Path | None:
    """Find a pre-built signed .app bundle installed by Homebrew.

    When installed via `brew install`, the formula puts the bundle at
    libexec/bundle/Dictare.app.  We find it by resolving the `dictare`
    binary symlink back to the Cellar.
    """
    try:
        dictare_bin = shutil.which("dictare")
        if not dictare_bin:
            return None
        # /opt/homebrew/bin/dictare → .../libexec/bin/dictare
        real_bin = Path(dictare_bin).resolve()
        libexec = real_bin.parent.parent
        candidate = libexec / "bundle" / f"{APP_NAME}.app"
        if candidate.is_dir() and (candidate / "Contents" / "MacOS" / APP_NAME).exists():
            return candidate
    except Exception:
        pass
    return None

def _install_cellar_bundle(src_bundle: Path, dest_bundle: Path) -> None:
    """Copy a complete signed .app bundle from the Cellar to ~/Applications."""
    if dest_bundle.exists():
        subprocess.run(["rm", "-rf", str(dest_bundle)], check=False, capture_output=True)
    dest_bundle.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_bundle, dest_bundle, symlinks=True)
    # Remove quarantine xattr
    subprocess.run(
        ["xattr", "-dr", "com.apple.quarantine", str(dest_bundle)],
        check=False, capture_output=True,
    )
    logger.info("Installed signed bundle: %s → %s", src_bundle, dest_bundle)

def _install_prebuilt_launcher(prebuilt: Path, dest: Path) -> bool:
    """Install a pre-built signed launcher binary.

    Returns True if the binary was copied and its code signature is valid.
    """
    if not prebuilt.exists():
        logger.warning("Pre-built launcher not found: %s", prebuilt)
        return False
    # Verify code signature on the SOURCE binary (not inside .app bundle,
    # where codesign would treat it as a bundle executable and expect resources).
    result = subprocess.run(
        ["codesign", "--verify", str(prebuilt)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.warning("Pre-built launcher signature invalid: %s", result.stderr)
        return False
    shutil.copy2(prebuilt, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
    # Remove quarantine — gh release download sets com.apple.quarantine on
    # downloaded files. Without this, macOS shows "damaged" on first launch.
    subprocess.run(
        ["xattr", "-d", "com.apple.quarantine", str(dest)],
        check=False, capture_output=True,
    )
    return True

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
