"""Isolated venv management for TTS engines.

Heavy TTS engines (piper, coqui, outetts) have dependencies that conflict
with STT engines (e.g., numba vs numpy version conflicts). Each engine gets
its own venv at ``~/.local/share/dictare/tts-env/{engine}/`` with only
the TTS package + minimal deps. The TTS worker subprocess uses the venv's
Python, and PYTHONPATH injects dictare's source so it can import
``dictare.tts.*`` without being installed in the venv.

After this, **any STT + any TTS** work together, zero dependency conflicts.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# Engines that need an isolated venv. Maps engine name → pip packages.
VENV_ENGINES: dict[str, list[str]] = {
    "piper": ["piper-tts", "pathvalidate"],
    "coqui": ["TTS"],
    "outetts": ["mlx-audio"],
    "kokoro": ["kokoro-onnx", "soundfile"],
}

# Shared deps installed in every TTS venv (needed by worker.py imports).
# openvip source is injected via PYTHONPATH, but its dependencies must be
# installed in the venv (they're not available via PYTHONPATH alone).
_SHARED_DEPS = ["pydantic", "urllib3", "python-dateutil", "typing-extensions"]

# Root directory for TTS venvs
_VENV_ROOT = Path.home() / ".local" / "share" / "dictare" / "tts-env"


def get_venv_dir(engine: str) -> Path:
    """Return the venv directory for a TTS engine.

    Args:
        engine: Engine name (piper, coqui, outetts).

    Returns:
        Path to ``~/.local/share/dictare/tts-env/{engine}/``.
    """
    return _VENV_ROOT / engine


def get_venv_python(engine: str) -> str | None:
    """Return the venv Python path if the venv is installed, else None.

    System engines (say, espeak) never use a venv — returns None.

    Args:
        engine: Engine name.

    Returns:
        Absolute path to the venv's Python, or None.
    """
    if engine not in VENV_ENGINES:
        return None
    venv_dir = get_venv_dir(engine)
    python = venv_dir / "bin" / "python"
    if python.exists():
        return str(python)
    return None


def get_venv_bin_dir(engine: str) -> Path | None:
    """Return the venv's bin directory if the venv exists.

    Args:
        engine: Engine name.

    Returns:
        Path to the venv's bin/ directory, or None.
    """
    if engine not in VENV_ENGINES:
        return None
    bin_dir = get_venv_dir(engine) / "bin"
    if bin_dir.is_dir():
        return bin_dir
    return None


def is_venv_installed(engine: str) -> bool:
    """Check if the isolated venv for an engine exists and has deps installed.

    Args:
        engine: Engine name.

    Returns:
        True if the venv exists and its Python is functional.
    """
    python = get_venv_python(engine)
    return python is not None


def get_worker_pythonpath() -> str:
    """Return PYTHONPATH for the TTS worker subprocess.

    The worker needs to import both ``dictare`` and ``openvip``. For
    site-packages installs (Homebrew, pip), both live in the same directory.
    For editable/dev installs, they may be in different source trees —
    we return both paths joined with ``os.pathsep``.

    Returns:
        Colon-separated (or semicolon on Windows) path string.
    """
    import os

    import dictare

    paths: set[str] = set()

    # dictare/__init__.py → dictare/ → parent (src/ or site-packages/)
    dictare_init = Path(dictare.__file__).resolve()
    paths.add(str(dictare_init.parent.parent))

    # openvip may live in a different source tree (editable install)
    try:
        import openvip

        openvip_init = Path(openvip.__file__).resolve()
        paths.add(str(openvip_init.parent.parent))
    except ImportError:
        pass  # Will fail in worker too — logged there

    return os.pathsep.join(sorted(paths))


def get_dictare_src_path() -> str:
    """Return the path to inject via PYTHONPATH so the worker can import dictare.

    .. deprecated:: 0.1.12
        Use :func:`get_worker_pythonpath` instead, which also includes openvip.
    """
    import dictare

    dictare_init = Path(dictare.__file__).resolve()
    return str(dictare_init.parent.parent)


def _find_uv() -> str | None:
    """Find the uv binary, including Homebrew paths not in launchd PATH."""
    uv = shutil.which("uv")
    if uv:
        return uv
    # launchd services have minimal PATH — check common Homebrew locations
    for path in ("/opt/homebrew/bin/uv", "/usr/local/bin/uv"):
        if Path(path).exists():
            return path
    return None


def install_venv(
    engine: str,
    on_progress: Callable[[str], None] | None = None,
) -> bool:
    """Create an isolated venv and install deps for a TTS engine.

    Args:
        engine: Engine name (must be in VENV_ENGINES).
        on_progress: Optional callback for progress messages.

    Returns:
        True if installation succeeded.
    """
    if engine not in VENV_ENGINES:
        raise ValueError(f"Unknown venv engine: {engine}")

    packages = VENV_ENGINES[engine]
    all_packages = packages + _SHARED_DEPS
    venv_dir = get_venv_dir(engine)

    def _log(msg: str) -> None:
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    try:
        # Create venv
        _log(f"Creating venv at {venv_dir}")
        venv_dir.parent.mkdir(parents=True, exist_ok=True)

        uv = _find_uv()
        if uv:
            subprocess.run(
                [uv, "venv", "--python", "3.11", str(venv_dir)],
                check=True,
                capture_output=True,
            )
        else:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
                capture_output=True,
            )

        # Install packages
        python = str(venv_dir / "bin" / "python")
        _log(f"Installing {', '.join(all_packages)}")

        if uv:
            subprocess.run(
                [uv, "pip", "install", "--python", python, *all_packages],
                check=True,
                capture_output=True,
            )
        else:
            subprocess.run(
                [python, "-m", "pip", "install", *all_packages],
                check=True,
                capture_output=True,
            )

        _log(f"TTS venv for '{engine}' installed successfully")
        return True

    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if exc.stderr else ""
        _log(f"Install failed: {stderr[:500]}")
        # Clean up partial venv
        if venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)
        return False
    except Exception as exc:
        _log(f"Install failed: {exc}")
        if venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)
        return False


def uninstall_venv(engine: str) -> bool:
    """Remove the isolated venv for a TTS engine.

    Args:
        engine: Engine name.

    Returns:
        True if removed (or didn't exist).
    """
    if engine not in VENV_ENGINES:
        raise ValueError(f"Unknown venv engine: {engine}")

    venv_dir = get_venv_dir(engine)
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
        logger.info("Removed TTS venv for '%s'", engine)
    return True
