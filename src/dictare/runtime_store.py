"""Dictare-owned runtime store.

The product runtime lives outside package-manager ownership:

    ~/.local/share/dictare/versions/<version>/
    ~/.local/share/dictare/current -> versions/<version>
    ~/.local/share/dictare/previous -> versions/<previous>

Installers and upgrade commands use this module so macOS and Linux share the
same lifecycle semantics.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dictare import __version__

RUNTIME_ROOT = Path.home() / ".local" / "share" / "dictare"
VERSIONS_DIR = RUNTIME_ROOT / "versions"
CURRENT_LINK = RUNTIME_ROOT / "current"
PREVIOUS_LINK = RUNTIME_ROOT / "previous"
LOCK_DIR = RUNTIME_ROOT / "locks"
BIN_DIR = Path.home() / ".local" / "bin"
SHIM_PATH = BIN_DIR / "dictare"


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Runtime store state visible to lifecycle commands."""

    current: Path | None
    previous: Path | None
    current_version: str | None
    previous_version: str | None
    shim: Path
    shim_exists: bool


def runtime_root() -> Path:
    """Return the runtime root."""
    return RUNTIME_ROOT


def current_runtime() -> Path | None:
    """Return the current runtime directory if configured."""
    if not CURRENT_LINK.exists():
        return None
    try:
        return CURRENT_LINK.resolve()
    except OSError:
        return None


def previous_runtime() -> Path | None:
    """Return the previous runtime directory if configured."""
    if not PREVIOUS_LINK.exists():
        return None
    try:
        return PREVIOUS_LINK.resolve()
    except OSError:
        return None


def runtime_python(runtime: Path | None = None) -> Path:
    """Return the Python executable for a runtime."""
    runtime = runtime or require_current_runtime()
    return runtime / "bin" / "python"


def runtime_dictare(runtime: Path | None = None) -> Path:
    """Return the dictare executable for a runtime."""
    runtime = runtime or require_current_runtime()
    return runtime / "bin" / "dictare"


def require_current_runtime() -> Path:
    """Return current runtime or raise a clear error."""
    runtime = current_runtime()
    if runtime is None:
        raise RuntimeError(
            "Dictare runtime store is not initialized. Reinstall with install.sh."
        )
    return runtime


def resolve_service_python_path(fallback: str | None = None) -> str | None:
    """Resolve the Python executable services should use.

    The Dictare runtime store wins over package-manager paths. Legacy callers
    can pass a fallback for development or old installs.
    """
    runtime = current_runtime()
    if runtime is not None:
        python = runtime_python(runtime)
        if python.exists():
            return str(python)
    return fallback


def snapshot() -> RuntimeSnapshot:
    """Return a snapshot of current runtime store state."""
    current = current_runtime()
    previous = previous_runtime()
    return RuntimeSnapshot(
        current=current,
        previous=previous,
        current_version=current.name if current else None,
        previous_version=previous.name if previous else None,
        shim=SHIM_PATH,
        shim_exists=SHIM_PATH.exists(),
    )


def ensure_dirs() -> None:
    """Create runtime store directories."""
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)


def default_extras() -> list[str]:
    """Return platform-appropriate default extras."""
    extras: list[str] = []
    if sys.platform == "darwin" and platform.machine() == "arm64":
        extras.append("mlx")
    elif sys.platform == "linux":
        extras.append("tray")
    return extras


def package_spec(version: str, extras: list[str] | None = None, source: str | None = None) -> str:
    """Build a pip-compatible package spec."""
    extras = extras if extras is not None else default_extras()
    extra_suffix = f"[{','.join(extras)}]" if extras else ""
    if source:
        return f"dictare{extra_suffix} @ {_source_to_url(source)}"
    return f"dictare{extra_suffix}=={version}"


def install_runtime(
    version: str = __version__,
    *,
    source: str | None = None,
    extras: list[str] | None = None,
    reinstall: bool = False,
) -> Path:
    """Install a runtime version next to any existing versions.

    Args:
        version: Version directory name.
        source: Optional local path or package URL.
        extras: Optional extras to install.
        reinstall: Reinstall package into an existing runtime.
    """
    ensure_dirs()
    target = VERSIONS_DIR / version
    if not target.exists():
        _run(["uv", "venv", "--python", "3.11", str(target)])
    elif not (target / "bin" / "python").exists():
        raise RuntimeError(f"Runtime directory is incomplete: {target}")

    extras = extras if extras is not None else default_extras()
    spec = package_spec(version, extras=extras, source=source)
    cmd = [
        "uv",
        "pip",
        "install",
        "--python",
        str(runtime_python(target)),
        "--prerelease=allow",
    ]
    if reinstall:
        cmd.append("--reinstall")
    cmd.append(spec)
    _run(cmd)
    smoke_test(target, expected_version=version)
    return target


def smoke_test(runtime: Path, expected_version: str | None = None) -> None:
    """Verify a runtime can launch dictare."""
    result = subprocess.run(
        [str(runtime_dictare(runtime)), "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    output = (result.stdout + result.stderr).strip()
    if expected_version and expected_version not in output:
        raise RuntimeError(
            f"Installed runtime reports unexpected version: {output!r} "
            f"(expected {expected_version})"
        )


def activate_runtime(runtime: Path) -> None:
    """Atomically make a runtime current and preserve the previous runtime."""
    ensure_dirs()
    old_current = current_runtime()
    if old_current is not None and old_current != runtime:
        _replace_symlink(PREVIOUS_LINK, old_current)
    _replace_symlink(CURRENT_LINK, runtime)
    ensure_shim()


def rollback_runtime() -> Path:
    """Flip current back to previous and return the activated runtime."""
    previous = previous_runtime()
    current = current_runtime()
    if previous is None:
        raise RuntimeError("No previous Dictare runtime is available for rollback.")
    if current is not None:
        _replace_symlink(PREVIOUS_LINK, current)
    _replace_symlink(CURRENT_LINK, previous)
    ensure_shim()
    return previous


def ensure_shim() -> Path:
    """Install the stable user-facing dictare shim."""
    ensure_dirs()
    script = """#!/usr/bin/env bash
set -euo pipefail
exec "$HOME/.local/share/dictare/current/bin/dictare" "$@"
"""
    if SHIM_PATH.exists():
        try:
            if SHIM_PATH.read_text() == script:
                return SHIM_PATH
        except UnicodeDecodeError:
            pass

    backup_existing_path(SHIM_PATH)
    SHIM_PATH.write_text(script)
    SHIM_PATH.chmod(0o755)
    return SHIM_PATH


def write_launcher_python_path() -> Path:
    """Write the macOS launcher compatibility python_path file."""
    config_dir = Path.home() / ".dictare"
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "python_path"
    target.write_text(str(runtime_python()))
    return target


def backup_existing_path(path: Path) -> Path | None:
    """Move an existing file/symlink aside under ~/.dictare/trash."""
    if not path.exists() and not path.is_symlink():
        return None
    trash = Path.home() / ".dictare" / "trash"
    trash.mkdir(parents=True, exist_ok=True)
    backup = trash / f"{path.name}.{os.getpid()}"
    counter = 0
    while backup.exists() or backup.is_symlink():
        counter += 1
        backup = trash / f"{path.name}.{os.getpid()}.{counter}"
    shutil.move(str(path), str(backup))
    return backup


def _replace_symlink(link: Path, target: Path) -> None:
    """Atomically replace a symlink."""
    link.parent.mkdir(parents=True, exist_ok=True)
    tmp = link.with_name(f".{link.name}.tmp.{os.getpid()}")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(target, target_is_directory=True)
    os.replace(tmp, link)


def _source_to_url(source: str) -> str:
    """Return a PEP 508-compatible URL for a source path or URL."""
    if "://" in source:
        return source
    return Path(source).expanduser().resolve().as_uri()


def _run(cmd: list[str]) -> None:
    """Run a subprocess with a readable error."""
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as e:
        raise RuntimeError(f"Required command not found: {cmd[0]}") from e
