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

def _check_python_version() -> list[CheckResult]:
    """Check Python version requirement."""
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    py_ok = sys.version_info >= (3, 11)
    return [
        CheckResult(
            name="Python",
            available=py_ok,
            message=f"Version {py_version}" + ("" if py_ok else " (need 3.11+)"),
        )
    ]

def _check_audio_deps() -> list[CheckResult]:
    """Check audio dependencies (sounddevice)."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        input_devices = [d for d in devices if d["max_input_channels"] > 0]  # type: ignore
        return [
            CheckResult(
                name="sounddevice",
                available=len(input_devices) > 0,
                message=f"Found {len(input_devices)} input device(s)",
            )
        ]
    except Exception as e:
        return [
            CheckResult(
                name="sounddevice",
                available=False,
                message=f"Error: {e}",
            )
        ]

def _check_stt_deps() -> list[CheckResult]:
    """Check STT dependencies (mlx-whisper on macOS, faster-whisper on Linux)."""
    if is_macos():
        try:
            import mlx_whisper  # noqa: F401

            return [
                CheckResult(
                    name="mlx-whisper",
                    available=True,
                    message="Installed (Apple Silicon GPU)",
                )
            ]
        except ImportError:
            return [
                CheckResult(
                    name="mlx-whisper",
                    available=False,
                    message="Not installed",
                    install_hint="uv tool install 'voxtype[mlx,macos]' --force",
                )
            ]
    else:
        try:
            import faster_whisper  # noqa: F401

            return [
                CheckResult(
                    name="faster-whisper",
                    available=True,
                    message="Installed",
                )
            ]
        except ImportError:
            return [
                CheckResult(
                    name="faster-whisper",
                    available=False,
                    message="Not installed",
                    install_hint="uv tool install 'voxtype[linux]' --force",
                )
            ]

def _check_hotkey_deps_linux() -> list[CheckResult]:
    """Check Linux hotkey dependencies (evdev)."""
    results: list[CheckResult] = []
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
                    message=f"Found {len(devices)} device(s)" if devices else "No access",
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
    return results

def _check_hotkey_deps_macos() -> list[CheckResult]:
    """Check macOS hotkey dependencies (pynput)."""
    try:
        import pynput  # noqa: F401

        return [
            CheckResult(
                name="pynput",
                available=True,
                message="Installed",
            )
        ]
    except ImportError:
        return [
            CheckResult(
                name="pynput",
                available=False,
                message="Not installed",
                install_hint="uv tool install 'voxtype[mlx,macos]' --force",
            )
        ]

def _check_injection_deps_linux() -> list[CheckResult]:
    """Check Linux text injection dependencies."""
    results: list[CheckResult] = []

    # ydotool
    ydotool_exists = check_command_exists("ydotool")
    ydotoold_running = check_ydotoold_running() if ydotool_exists else False

    if ydotool_exists and ydotoold_running:
        msg, hint = "Ready", None
    elif ydotool_exists:
        msg, hint = "ydotoold not running", "systemctl --user start ydotoold"
    else:
        msg, hint = "Not installed", "See install-linux.sh in the repo"

    results.append(
        CheckResult(
            name="ydotool",
            available=ydotool_exists and ydotoold_running,
            message=msg,
            required=False,
            install_hint=hint,
        )
    )

    return results

def _check_injection_deps_macos() -> list[CheckResult]:
    """Check macOS text injection dependencies."""
    return [
        CheckResult(
            name="osascript",
            available=check_command_exists("osascript"),
            message="Available (built-in)",
        ),
        CheckResult(
            name="pbcopy",
            available=check_command_exists("pbcopy"),
            message="Available (built-in)",
        ),
    ]

def _check_display_deps() -> list[CheckResult]:
    """Check display server info (Linux only)."""
    if not is_linux():
        return []

    if is_wayland():
        msg = "Wayland"
    elif is_x11():
        msg = "X11"
    else:
        msg = "Console (no display server)"

    return [
        CheckResult(
            name="Display",
            available=True,
            message=msg,
            required=False,
        )
    ]

def _check_gpu_deps() -> list[CheckResult]:
    """Check GPU/hardware acceleration dependencies."""
    results: list[CheckResult] = []

    if is_linux():
        # Check for NVIDIA GPU
        try:
            from voxtype.cuda_setup import check_gpu_available, _find_cudnn_path

            gpu_ok, gpu_count = check_gpu_available()

            if gpu_ok:
                # GPU found, check cuDNN
                cudnn_path = _find_cudnn_path()
                if cudnn_path:
                    results.append(
                        CheckResult(
                            name="NVIDIA GPU",
                            available=True,
                            message=f"{gpu_count} device(s), cuDNN ready",
                            required=False,
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            name="NVIDIA GPU",
                            available=False,
                            message=f"{gpu_count} device(s), cuDNN missing",
                            required=False,
                            install_hint="uv tool install voxtype --with 'nvidia-cudnn-cu12>=9.1.0,<9.2.0'",
                        )
                    )
            else:
                results.append(
                    CheckResult(
                        name="NVIDIA GPU",
                        available=False,
                        message="Not detected (using CPU)",
                        required=False,
                    )
                )
        except Exception:
            results.append(
                CheckResult(
                    name="NVIDIA GPU",
                    available=False,
                    message="Check failed",
                    required=False,
                )
            )

    elif is_macos():
        # Check for Apple Silicon + MLX
        import platform

        is_arm = platform.machine() == "arm64"

        if is_arm:
            try:
                import mlx_whisper  # noqa: F401

                results.append(
                    CheckResult(
                        name="Apple Silicon",
                        available=True,
                        message="MLX ready",
                        required=False,
                    )
                )
            except ImportError:
                results.append(
                    CheckResult(
                        name="Apple Silicon",
                        available=False,
                        message="MLX not installed",
                        required=False,
                        install_hint="uv tool install voxtype --with 'mlx-whisper>=0.4.0'",
                    )
                )
        else:
            results.append(
                CheckResult(
                    name="Apple Silicon",
                    available=False,
                    message="Intel Mac (no MLX)",
                    required=False,
                )
            )

    return results

def check_dependencies() -> list[CheckResult]:
    """Check all system dependencies.

    Returns:
        List of check results for each dependency.
    """
    results: list[CheckResult] = []

    results.extend(_check_python_version())
    results.extend(_check_audio_deps())
    results.extend(_check_stt_deps())
    results.extend(_check_gpu_deps())

    if is_linux():
        results.extend(_check_hotkey_deps_linux())
        results.extend(_check_injection_deps_linux())
    elif is_macos():
        results.extend(_check_hotkey_deps_macos())
        results.extend(_check_injection_deps_macos())

    results.extend(_check_display_deps())

    return results
