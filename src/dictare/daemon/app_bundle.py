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
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "Dictare"
BUNDLE_ID = "dev.dragfly.dictare"


def _candidate_brew_python_paths() -> list[Path]:
    """Return stable Homebrew opt-prefix Python candidates.

    The Swift launcher reads ``~/.dictare/python_path`` before Python starts.
    That makes this file part of the pre-launch contract: for Homebrew installs
    it must contain the stable ``opt`` path, not a versioned Cellar path and not
    a local development venv.
    """
    return [
        Path("/opt/homebrew/opt/dictare/libexec/uv-tools/dictare/bin/python"),
        Path("/usr/local/opt/dictare/libexec/uv-tools/dictare/bin/python"),
    ]

def _candidate_homebrew_bundle_paths() -> list[Path]:
    """Return Homebrew-installed signed bundle candidates.

    The runtime-store installer can create ``~/.local/bin/dictare``. If that
    shim appears before Homebrew in PATH, resolving ``dictare`` is not enough to
    find the signed bundle. Prefer the explicit wrapper hint and stable Homebrew
    opt paths before falling back to PATH.
    """
    candidates: list[Path] = []
    env_bundle = os.environ.get("DICTARE_HOMEBREW_BUNDLE")
    if env_bundle:
        candidates.append(Path(env_bundle).expanduser())
    hint_file = Path.home() / ".dictare" / "homebrew_bundle_path"
    try:
        hinted_bundle = hint_file.read_text().strip()
    except OSError:
        hinted_bundle = ""
    if hinted_bundle:
        candidates.append(Path(hinted_bundle).expanduser())
    candidates.extend(
        [
            Path("/opt/homebrew/opt/dictare/libexec/bundle/Dictare.app"),
            Path("/usr/local/opt/dictare/libexec/bundle/Dictare.app"),
        ]
    )
    return candidates

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
    if python_path is None:
        python_path = sys.executable
    python_path = resolve_service_python_path(python_path)

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

def resolve_python_path(
    current_executable: str,
    stored_path: str | None,
) -> tuple[str, bool]:
    """Decide which Python path to use for the launcher.

    Compares the currently running Python (sys.executable) with the
    stored path in ~/.dictare/python_path.  Returns the path to use
    and whether it changed (needs writing).

    Args:
        current_executable: The Python running right now (sys.executable).
        stored_path: The path currently in ~/.dictare/python_path, or None
                     if the file doesn't exist.

    Returns:
        (path, changed): The resolved path and whether it differs from stored.
    """
    if not stored_path or not stored_path.strip():
        # First run or empty/corrupt file — no valid stored path
        return current_executable, True

    stored = stored_path.strip()

    if stored == current_executable:
        # Already correct — no change needed
        return current_executable, False

    # Paths differ as strings. Check if they point to the same binary (different
    # symlink names for the same file, e.g. 'python' vs 'python3.11' in same dir).
    from pathlib import Path

    try:
        if Path(stored).resolve() == Path(current_executable).resolve():
            # Same binary, just different symlink name — keep stored, no rewrite
            return stored, False
    except (OSError, RuntimeError):
        pass

    # Path changed (brew upgrade, reinstall, etc.)
    return current_executable, True


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


def find_brew_python() -> str | None:
    """Return the Homebrew-installed dictare's Python interpreter path, if present.

    When the Homebrew formula installs dictare, the layout is:

        <brew-prefix>/bin/dictare                         (symlink in PATH)
            └─→ <brew-prefix>/Cellar/dictare/<version>/libexec/bin/dictare
        <brew-prefix>/Cellar/dictare/<version>/libexec/uv-tools/dictare/bin/python
                                                          (the venv interpreter)

    We resolve `dictare` on PATH and require it to live under
    `…/Cellar/dictare/<v>/libexec/bin/dictare`. The brew prefix is not
    hard-coded — works for `/opt/homebrew` (Apple Silicon), `/usr/local`
    (Intel), and custom installations.

    Returns None when dictare is not installed via Homebrew (dev mode,
    pyenv editable install, manual venv, etc.), so callers can fall back
    to other resolution strategies.
    """
    for candidate in _candidate_brew_python_paths():
        if candidate.is_file():
            return str(candidate)

    try:
        dictare_bin = shutil.which("dictare")
        if not dictare_bin:
            return None
        real_bin = Path(dictare_bin).resolve()
        parts = real_bin.parts

        # Require the brew Cellar layout: `…/Cellar/dictare/<v>/libexec/bin/dictare`.
        try:
            cellar_idx = parts.index("Cellar")
        except ValueError:
            return None
        if parts[cellar_idx:cellar_idx + 2] != ("Cellar", "dictare"):
            return None
        if parts[cellar_idx + 3:cellar_idx + 6] != ("libexec", "bin", "dictare"):
            return None

        # Translate `…/libexec/bin/dictare` → `…/libexec/uv-tools/dictare/bin/python`.
        libexec = real_bin.parent.parent
        python = libexec / "uv-tools" / "dictare" / "bin" / "python"
        if python.is_file():
            return str(python)
    except OSError:
        # shutil.which / resolve() can raise on permission errors or broken symlinks.
        pass
    return None


def resolve_service_python_path(executable: str | None = None) -> str:
    """Resolve the interpreter launchd/launcher should use.

    The Dictare runtime store is authoritative for the new installer. Homebrew
    remains a legacy fallback for old installs. For Homebrew installs, prefer
    the stable opt interpreter so old Cellar paths do not leak into launchd.
    """
    try:
        from dictare.runtime_store import resolve_service_python_path as resolve_runtime_python

        runtime_python = resolve_runtime_python(None)
        if runtime_python:
            return runtime_python
    except Exception:
        pass

    brew_python = find_brew_python()
    if brew_python is not None:
        return brew_python
    return executable or sys.executable


def sync_service_python_path(executable: str | None = None) -> str:
    """Write the pre-launch Python path and return it."""
    python_path = resolve_service_python_path(executable)
    config_dir = Path.home() / ".dictare"
    target = config_dir / "python_path"
    stored = target.read_text().strip() if target.exists() else None
    if stored != python_path:
        logger.info("syncing python_path for launcher: %s → %s", stored, python_path)
        _write_external_python_path(python_path)
    return python_path


def ensure_python_path(executable: str) -> None:
    """Self-healing: ensure ~/.dictare/python_path points to the right interpreter.

    Resolution priority:

    1. **Runtime store wins.** The product-owned runtime under
       ``~/.local/share/dictare/current`` is authoritative for current installs.

    2. **Legacy Homebrew fallback.** If no runtime store exists, older
       Homebrew-owned installs can still pin the launcher to the brew venv's
       python instead of a stray pyenv or development interpreter.

    3. **Otherwise, accept the currently running interpreter** (dev mode):
       this matches the pre-existing behavior — useful for handling brew
       upgrades (Cellar version bumps) and dev workflows where there is
       no brew install at all.
    """
    config_dir = Path.home() / ".dictare"
    target = config_dir / "python_path"
    stored = target.read_text().strip() if target.exists() else None

    try:
        from dictare.runtime_store import resolve_service_python_path as resolve_runtime_python

        runtime_python = resolve_runtime_python(None)
        if runtime_python and stored != runtime_python:
            logger.info("python_path: pinning to Dictare runtime store %s", runtime_python)
            _write_external_python_path(runtime_python)
            return
        if runtime_python:
            return
    except Exception:
        pass

    # Step 2: legacy brew installation fallback.
    service_python = resolve_service_python_path(executable)
    if service_python != executable:
        if stored == service_python:
            return
        logger.info(
            "python_path: brew install detected, pinning to %s (was %s)",
            service_python, stored,
        )
        _write_external_python_path(service_python)
        return

    # Step 3: no brew → preserve existing self-healing behavior.
    resolved, changed = resolve_python_path(executable, stored)
    if changed:
        logger.info("Updating python_path: %s → %s", stored, resolved)
        _write_external_python_path(resolved)

def _find_cellar_bundle() -> Path | None:
    """Find a pre-built signed .app bundle installed by Homebrew.

    When installed via `brew install`, the formula puts the bundle at
    libexec/bundle/Dictare.app.  We find it by resolving the `dictare`
    binary symlink back to the Cellar.  Runtime-store installs may put the
    user shim earlier in PATH, so explicit Homebrew bundle hints are checked
    first.
    """
    for candidate in _candidate_homebrew_bundle_paths():
        if _is_valid_bundle(candidate):
            return candidate

    try:
        dictare_bin = shutil.which("dictare")
        if not dictare_bin:
            return None
        # /opt/homebrew/bin/dictare → .../libexec/bin/dictare
        real_bin = Path(dictare_bin).resolve()
        libexec = real_bin.parent.parent
        candidate = libexec / "bundle" / f"{APP_NAME}.app"
        if _is_valid_bundle(candidate):
            return candidate
    except Exception:
        pass
    return None

def _is_valid_bundle(candidate: Path) -> bool:
    return (
        candidate.is_dir()
        and (candidate / "Contents" / "MacOS" / APP_NAME).exists()
    )

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


def migrate_signed_bundle_from_cellar(force: bool = False) -> bool:
    """Move an old user app aside and install the signed Cellar bundle.

    Returns True when a migration happened. This is a legacy Homebrew repair
    helper for users with an ad-hoc app bundle in ~/Applications.
    """
    src = _find_cellar_bundle()
    if src is None:
        return False

    dest = get_app_path()
    signed_marker = dest / "Contents" / "Resources" / "launcher_signed"
    if dest.exists() and signed_marker.exists() and not force:
        return False

    if dest.exists():
        trash = Path.home() / ".dictare" / "trash"
        trash.mkdir(parents=True, exist_ok=True)
        backup = trash / f"Dictare.app.{int(time.time())}"
        counter = 0
        while backup.exists():
            counter += 1
            backup = trash / f"Dictare.app.{int(time.time())}.{counter}"
        shutil.move(str(dest), str(backup))

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, symlinks=True)
    subprocess.run(
        ["xattr", "-dr", "com.apple.quarantine", str(dest)],
        check=False,
        capture_output=True,
    )
    logger.info("Migrated signed bundle: %s → %s", src, dest)
    return True

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
