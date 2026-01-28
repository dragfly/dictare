"""Installation detection and dependency commands."""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path


class InstallMode(Enum):
    """How voxtype was installed."""

    UV_TOOL = "uv_tool"  # uv tool install voxtype
    PIPX = "pipx"  # pipx install voxtype
    PIP = "pip"  # pip install voxtype
    DEV = "dev"  # pip install -e . or uv pip install -e .
    UNKNOWN = "unknown"


def detect_install_mode() -> InstallMode:
    """Detect how voxtype was installed.

    Returns:
        InstallMode indicating the installation method.
    """
    # Use voxtype's own path to detect installation mode
    try:
        import voxtype

        voxtype_path = str(Path(voxtype.__file__).resolve())

        # Check for uv tool installation FIRST (highest priority)
        # uv tool installs to ~/.local/share/uv/tools/voxtype/lib/.../site-packages/
        if ".local/share/uv/tools" in voxtype_path:
            return InstallMode.UV_TOOL

        # Check for pipx installation
        # pipx installs to ~/.local/pipx/venvs/voxtype/lib/.../site-packages/
        if ".local/pipx/venvs" in voxtype_path:
            return InstallMode.PIPX

        # Check if running from editable install (dev mode)
        # Editable installs have __file__ pointing to source directory, not site-packages
        if "site-packages" not in voxtype_path:
            return InstallMode.DEV

    except Exception:
        pass

    # Check if in a virtualenv/venv (regular pip install)
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        return InstallMode.PIP

    return InstallMode.UNKNOWN


def get_install_command(package: str, mode: InstallMode | None = None) -> str:
    """Get the command to install an optional dependency.

    Args:
        package: Package name (e.g., 'piper-tts', 'TTS').
        mode: Installation mode. Auto-detected if None.

    Returns:
        Command string to install the package.
    """
    if mode is None:
        mode = detect_install_mode()

    if mode == InstallMode.UV_TOOL:
        # For uv tool, install directly into the tool's environment
        tool_python = Path.home() / ".local/share/uv/tools/voxtype/bin/python"
        return f"uv pip install --python {tool_python} {package}"

    commands = {
        InstallMode.PIPX: f"pipx inject voxtype {package}",
        InstallMode.PIP: f"pip install {package}",
        InstallMode.DEV: f"uv pip install {package}",
        InstallMode.UNKNOWN: f"pip install {package}",
    }

    return commands[mode]


def get_dependency_install_message(dependency: str, purpose: str = "") -> str:
    """Get a user-friendly message for installing a missing dependency.

    Args:
        dependency: Package name (e.g., 'piper-tts').
        purpose: Optional description of what it's for.

    Returns:
        Formatted message with install command.
    """
    mode = detect_install_mode()
    cmd = get_install_command(dependency, mode)

    purpose_str = f" for {purpose}" if purpose else ""

    return f"  Install{purpose_str}: {cmd}"


# Mapping of optional features to their dependencies
OPTIONAL_DEPENDENCIES = {
    # TTS engines
    "piper": ("piper-tts", "Piper neural TTS"),
    "coqui": ("TTS", "Coqui XTTS neural TTS"),
    "qwen3": ("mlx-audio", "Qwen3 TTS - NOT WORKING with mlx-audio yet"),
    "outetts": ("mlx-audio", "OuteTTS neural TTS (Apple Silicon)"),
    # Hardware acceleration
    "mlx": ("mlx-whisper>=0.4.0", "Apple Silicon MLX acceleration"),
    "cuda": ("nvidia-cudnn-cu12>=9.1.0,<9.2.0", "NVIDIA CUDA acceleration"),
    # Input backends
    "evdev": ("evdev", "Linux keyboard/device input"),
    "pynput": ("pynput", "macOS/X11 keyboard input"),
    "hidapi": ("hidapi", "HID device access"),
}


def get_feature_install_message(feature: str) -> str:
    """Get install message for an optional feature.

    Args:
        feature: Feature name (e.g., 'piper', 'coqui', 'mlx').

    Returns:
        Formatted install message.
    """
    if feature not in OPTIONAL_DEPENDENCIES:
        return f"  Unknown feature: {feature}"

    package, description = OPTIONAL_DEPENDENCIES[feature]
    return get_dependency_install_message(package, description)
