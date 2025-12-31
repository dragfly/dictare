"""Platform detection and dependency checking utilities."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field

@dataclass
class CheckResult:
    """Result of a dependency check."""

    name: str
    available: bool
    message: str
    required: bool = True
    install_hint: str | None = None

def is_linux() -> bool:
    """Check if running on Linux."""
    return sys.platform == "linux"

def is_macos() -> bool:
    """Check if running on macOS."""
    return sys.platform == "darwin"

def is_wayland() -> bool:
    """Check if running under Wayland."""
    import os

    return bool(os.environ.get("WAYLAND_DISPLAY"))

def is_x11() -> bool:
    """Check if running under X11."""
    import os

    return bool(os.environ.get("DISPLAY")) and not is_wayland()

def check_command_exists(command: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(command) is not None

def check_ydotoold_running() -> bool:
    """Check if ydotoold daemon is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "ydotoold"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def check_dependencies() -> list[CheckResult]:
    """Check all system dependencies.

    Returns:
        List of check results for each dependency.
    """
    results: list[CheckResult] = []

    # Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    py_ok = sys.version_info >= (3, 11)
    results.append(
        CheckResult(
            name="Python",
            available=py_ok,
            message=f"Version {py_version}" + ("" if py_ok else " (need 3.11+)"),
        )
    )

    # Audio libraries
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        input_devices = [d for d in devices if d["max_input_channels"] > 0]  # type: ignore
        results.append(
            CheckResult(
                name="sounddevice",
                available=len(input_devices) > 0,
                message=f"Found {len(input_devices)} input device(s)",
            )
        )
    except Exception as e:
        results.append(
            CheckResult(
                name="sounddevice",
                available=False,
                message=f"Error: {e}",
            )
        )

    # STT - platform specific
    if is_macos():
        # macOS uses mlx-whisper
        try:
            import mlx_whisper  # noqa: F401

            results.append(
                CheckResult(
                    name="mlx-whisper",
                    available=True,
                    message="Installed (Apple Silicon GPU)",
                )
            )
        except ImportError:
            results.append(
                CheckResult(
                    name="mlx-whisper",
                    available=False,
                    message="Not installed",
                    install_hint="uv tool install 'voxtype[mlx,macos]' --force",
                )
            )
    else:
        # Linux uses faster-whisper
        try:
            import faster_whisper  # noqa: F401

            results.append(
                CheckResult(
                    name="faster-whisper",
                    available=True,
                    message="Installed",
                )
            )
        except ImportError:
            results.append(
                CheckResult(
                    name="faster-whisper",
                    available=False,
                    message="Not installed",
                    install_hint="uv tool install 'voxtype[linux]' --force",
                )
            )

    # Hotkey detection (Linux)
    if is_linux():
        try:
            import evdev  # noqa: F401

            results.append(
                CheckResult(
                    name="evdev",
                    available=True,
                    message="Installed",
                    required=False,
                )
            )

            # Check input device access
            try:
                from evdev import list_devices

                devices = list_devices()
                results.append(
                    CheckResult(
                        name="Input devices",
                        available=len(devices) > 0,
                        message=f"Found {len(devices)} device(s)"
                        if devices
                        else "No access",
                        install_hint="sudo usermod -aG input $USER && newgrp input",
                    )
                )
            except PermissionError:
                results.append(
                    CheckResult(
                        name="Input devices",
                        available=False,
                        message="Permission denied",
                        install_hint="sudo usermod -aG input $USER && newgrp input",
                    )
                )
        except ImportError:
            results.append(
                CheckResult(
                    name="evdev",
                    available=False,
                    message="Not installed",
                    required=False,
                    install_hint="uv tool install 'voxtype[linux]' --force",
                )
            )

    # macOS hotkey
    if is_macos():
        try:
            import pynput  # noqa: F401

            results.append(
                CheckResult(
                    name="pynput",
                    available=True,
                    message="Installed",
                )
            )
        except ImportError:
            results.append(
                CheckResult(
                    name="pynput",
                    available=False,
                    message="Not installed",
                    install_hint="uv tool install 'voxtype[mlx,macos]' --force",
                )
            )

    # Text injection
    if is_linux():
        # ydotool
        ydotool_exists = check_command_exists("ydotool")
        ydotoold_running = check_ydotoold_running() if ydotool_exists else False

        if ydotool_exists and ydotoold_running:
            msg = "Ready"
            hint = None
        elif ydotool_exists:
            msg = "ydotoold not running"
            hint = "systemctl --user start ydotoold"
        else:
            msg = "Not installed"
            hint = "See install-linux.sh in the repo"

        results.append(
            CheckResult(
                name="ydotool",
                available=ydotool_exists and ydotoold_running,
                message=msg,
                required=False,
                install_hint=hint,
            )
        )

        # wtype (Wayland)
        wtype_exists = check_command_exists("wtype")
        results.append(
            CheckResult(
                name="wtype",
                available=wtype_exists,
                message="Available" if wtype_exists else "Not installed",
                required=False,
                install_hint="sudo apt install wtype" if not wtype_exists else None,
            )
        )

        # xdotool (X11)
        xdotool_exists = check_command_exists("xdotool")
        results.append(
            CheckResult(
                name="xdotool",
                available=xdotool_exists,
                message="Available" if xdotool_exists else "Not installed",
                required=False,
                install_hint="sudo apt install xdotool" if not xdotool_exists else None,
            )
        )

        # Clipboard tools
        wl_copy = check_command_exists("wl-copy")
        xclip = check_command_exists("xclip")
        results.append(
            CheckResult(
                name="Clipboard",
                available=wl_copy or xclip,
                message="wl-copy" if wl_copy else ("xclip" if xclip else "Not available"),
                required=False,
                install_hint="sudo apt install wl-clipboard" if not (wl_copy or xclip) else None,
            )
        )

    elif is_macos():
        results.append(
            CheckResult(
                name="osascript",
                available=check_command_exists("osascript"),
                message="Available (built-in)",
            )
        )
        results.append(
            CheckResult(
                name="pbcopy",
                available=check_command_exists("pbcopy"),
                message="Available (built-in)",
            )
        )

    # Display server info
    if is_linux():
        if is_wayland():
            results.append(
                CheckResult(
                    name="Display",
                    available=True,
                    message="Wayland",
                    required=False,
                )
            )
        elif is_x11():
            results.append(
                CheckResult(
                    name="Display",
                    available=True,
                    message="X11",
                    required=False,
                )
            )
        else:
            results.append(
                CheckResult(
                    name="Display",
                    available=True,
                    message="Console (no display server)",
                    required=False,
                )
            )

    return results
