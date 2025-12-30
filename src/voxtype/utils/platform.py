"""Platform detection and dependency checking utilities."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class CheckResult:
    """Result of a dependency check."""

    name: str
    available: bool
    message: str
    required: bool = True


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
    py_ok = sys.version_info >= (3, 10)
    results.append(
        CheckResult(
            name="Python",
            available=py_ok,
            message=f"Version {py_version}" + ("" if py_ok else " (need 3.10+)"),
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

    # STT
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
                    required=False,  # Optional, pynput can be used as fallback
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
                        else "No access (add user to 'input' group)",
                    )
                )
            except PermissionError:
                results.append(
                    CheckResult(
                        name="Input devices",
                        available=False,
                        message="Permission denied (add user to 'input' group)",
                    )
                )
        except ImportError:
            results.append(
                CheckResult(
                    name="evdev",
                    available=False,
                    message="Not installed (pip install evdev)",
                    required=False,  # Optional, pynput can be used as fallback
                )
            )

    # Text injection
    if is_linux():
        # ydotool
        ydotool_exists = check_command_exists("ydotool")
        ydotoold_running = check_ydotoold_running() if ydotool_exists else False
        results.append(
            CheckResult(
                name="ydotool",
                available=ydotool_exists and ydotoold_running,
                message="Ready"
                if (ydotool_exists and ydotoold_running)
                else ("ydotoold not running" if ydotool_exists else "Not installed"),
                required=False,
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
