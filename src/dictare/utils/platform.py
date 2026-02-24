"""Platform detection and dependency checking utilities."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def get_runtime_dir() -> Path:
    """Get the runtime directory for sockets and ephemeral files.

    Returns platform-appropriate directory:
    - Linux: $XDG_RUNTIME_DIR (typically /run/user/UID)
    - macOS: $TMPDIR (typically /var/folders/.../T/)
    - Fallback: /tmp

    This follows the de facto standard for Unix socket locations.
    """
    # Linux: XDG standard
    if xdg := os.environ.get("XDG_RUNTIME_DIR"):
        runtime_dir = Path(xdg)
        if runtime_dir.exists():
            return runtime_dir

    # macOS: user-specific temp directory
    if tmpdir := os.environ.get("TMPDIR"):
        runtime_dir = Path(tmpdir)
        if runtime_dir.exists():
            return runtime_dir

    # Fallback to /tmp
    return Path("/tmp")


def get_socket_dir() -> Path:
    """Get the directory for Dictare Unix sockets.

    Creates a dictare subdirectory in the runtime dir for organization.
    """
    socket_dir = get_runtime_dir() / "dictare"
    socket_dir.mkdir(parents=True, exist_ok=True)
    return socket_dir


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
                    install_hint="uv tool install 'dictare[mlx,macos]' --force",
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
                    install_hint="uv tool install 'dictare[linux]' --force",
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
                install_hint="uv tool install 'dictare[linux]' --force",
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
                install_hint="uv tool install 'dictare[mlx,macos]' --force",
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
            from dictare.cuda_setup import _find_cudnn_path, check_gpu_available

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
                            install_hint="uv tool install dictare --with 'nvidia-cudnn-cu12>=9.1.0,<9.2.0'",
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
                        install_hint="uv tool install dictare --with 'mlx-whisper>=0.4.0'",
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


def _check_tts_deps() -> list[CheckResult]:
    """Check TTS engine dependency based on user config."""
    from dictare.config import load_config

    results: list[CheckResult] = []

    try:
        config = load_config()
    except Exception:
        return results

    engine = config.tts.engine

    # System engines (espeak, say) — check binary is installed
    if engine in ("espeak", "say"):
        if check_command_exists(engine):
            results.append(CheckResult(
                name=f"TTS ({engine})",
                available=True,
                message="Available (system)",
                required=False,
            ))
        else:
            hint = f"brew install {engine}" if is_macos() else f"sudo apt install {engine}"
            results.append(CheckResult(
                name=f"TTS ({engine})",
                available=False,
                message=f"'{engine}' not found in PATH",
                required=False,
                install_hint=hint,
            ))
        return results

    from dictare.tts import create_tts_engine
    from dictare.utils.install_info import (
        OPTIONAL_DEPENDENCIES,
        get_install_command,
    )

    try:
        tts = create_tts_engine(config.tts)
        if tts.is_available():
            results.append(CheckResult(
                name=f"TTS ({engine})",
                available=True,
                message="Available",
                required=False,
            ))
        else:
            raise ValueError("not available")
    except (ValueError, Exception):
        dep_info = OPTIONAL_DEPENDENCIES.get(engine)
        hint = get_install_command(dep_info[0]) if dep_info else None  # type: ignore[assignment]
        results.append(CheckResult(
            name=f"TTS ({engine})",
            available=False,
            message=f"Configured engine '{engine}' not available",
            required=False,
            install_hint=hint,
        ))

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
    results.extend(_check_tts_deps())
    results.extend(_check_gpu_deps())

    if is_linux():
        results.extend(_check_hotkey_deps_linux())
        results.extend(_check_injection_deps_linux())
    elif is_macos():
        results.extend(_check_hotkey_deps_macos())
        results.extend(_check_injection_deps_macos())

    results.extend(_check_display_deps())

    return results


# ---------------------------------------------------------------------------
# All-engine health checks (for `dictare status` and Dashboard UI)
# ---------------------------------------------------------------------------

@dataclass
class EngineStatus:
    """Availability status of a single engine."""

    name: str
    available: bool
    description: str
    platform_ok: bool
    install_hint: str
    configured: bool = False
    venv_installed: bool = False
    needs_venv: bool = False

    def to_dict(self) -> dict:
        """Serialize for JSON API."""
        return {
            "name": self.name,
            "available": self.available,
            "description": self.description,
            "platform_ok": self.platform_ok,
            "install_hint": self.install_hint,
            "configured": self.configured,
            "venv_installed": self.venv_installed,
            "needs_venv": self.needs_venv,
        }


def _find_in_python_bin(name: str) -> bool:
    """Check if a script exists in the same dir as the Python executable."""
    python_bin = Path(sys.executable).parent
    return (python_bin / name).exists()


def check_all_tts_engines(configured_engine: str = "") -> list[dict]:
    """Probe every TTS engine and return availability info.

    Lightweight checks only — no heavy imports, no model loading.

    Args:
        configured_engine: Currently configured TTS engine name (for the 'configured' flag).

    Returns:
        List of dicts with name, available, description, platform_ok, install_hint, configured.
    """
    from dictare.tts.venv import VENV_ENGINES, get_venv_bin_dir, is_venv_installed
    from dictare.utils.install_info import get_install_command

    results: list[EngineStatus] = []

    # --- say (macOS only) ---
    say_platform = sys.platform == "darwin"
    say_available = say_platform and shutil.which("say") is not None
    results.append(EngineStatus(
        name="say",
        available=say_available,
        description="macOS built-in",
        platform_ok=say_platform,
        install_hint="" if say_platform else "macOS only",
        configured=configured_engine == "say",
    ))

    # --- espeak ---
    espeak_available = (
        shutil.which("espeak-ng") is not None
        or shutil.which("espeak") is not None
        # Fallback: launchd services don't inherit Homebrew PATH
        or Path("/opt/homebrew/bin/espeak-ng").exists()
        or Path("/usr/local/bin/espeak-ng").exists()
    )
    if espeak_available:
        hint = ""
    elif is_macos():
        hint = "brew install espeak-ng"
    else:
        hint = "sudo apt install espeak-ng"
    results.append(EngineStatus(
        name="espeak",
        available=espeak_available,
        description="espeak-ng speech synthesizer",
        platform_ok=True,
        install_hint=hint,
        configured=configured_engine == "espeak",
    ))

    # --- piper ---
    piper_venv = is_venv_installed("piper")
    piper_venv_bin = get_venv_bin_dir("piper")
    piper_available = (
        shutil.which("piper") is not None
        or shutil.which("piper-tts") is not None
        or _find_in_python_bin("piper")
        or (piper_venv_bin is not None and (piper_venv_bin / "piper").exists())
    )
    results.append(EngineStatus(
        name="piper",
        available=piper_available,
        description="Piper neural TTS",
        platform_ok=True,
        install_hint="" if piper_available else get_install_command("piper-tts"),
        configured=configured_engine == "piper",
        needs_venv="piper" in VENV_ENGINES,
        venv_installed=piper_venv,
    ))

    # --- coqui ---
    coqui_venv = is_venv_installed("coqui")
    coqui_venv_bin = get_venv_bin_dir("coqui")
    coqui_available = (
        shutil.which("tts") is not None
        or _find_in_python_bin("tts")
        or (coqui_venv_bin is not None and (coqui_venv_bin / "tts").exists())
    )
    results.append(EngineStatus(
        name="coqui",
        available=coqui_available,
        description="Coqui XTTS neural TTS",
        platform_ok=True,
        install_hint="" if coqui_available else get_install_command("TTS"),
        configured=configured_engine == "coqui",
        needs_venv="coqui" in VENV_ENGINES,
        venv_installed=coqui_venv,
    ))

    # --- outetts (Apple Silicon only) ---
    from dictare.utils.hardware import is_apple_silicon

    outetts_platform = is_apple_silicon()
    outetts_venv = is_venv_installed("outetts")
    outetts_available = False
    if outetts_platform:
        try:
            from importlib.util import find_spec
            outetts_available = find_spec("mlx_audio") is not None
        except (ImportError, ModuleNotFoundError):
            pass
        # Also check the venv for mlx-audio availability
        if not outetts_available and outetts_venv:
            outetts_available = True
    results.append(EngineStatus(
        name="outetts",
        available=outetts_available,
        description="OuteTTS via mlx-audio (Apple Silicon)",
        platform_ok=outetts_platform,
        install_hint=(
            "" if outetts_available
            else ("Apple Silicon only" if not outetts_platform
                  else get_install_command("mlx-audio"))
        ),
        configured=configured_engine == "outetts",
        needs_venv="outetts" in VENV_ENGINES,
        venv_installed=outetts_venv,
    ))

    return [r.to_dict() for r in results]


def check_all_stt_engines(configured_model: str = "") -> list[dict]:
    """Probe every STT backend and return availability info.

    Args:
        configured_model: Currently configured STT model name.

    Returns:
        List of dicts with name, available, description, platform_ok, install_hint, configured.
    """
    from importlib.util import find_spec

    from dictare.utils.hardware import is_apple_silicon
    from dictare.utils.install_info import get_install_command

    results: list[EngineStatus] = []
    is_parakeet_model = configured_model.startswith("parakeet")
    is_whisper_model = not is_parakeet_model and configured_model != ""

    # --- parakeet (onnx-asr) ---
    parakeet_available = find_spec("onnx_asr") is not None
    results.append(EngineStatus(
        name="parakeet",
        available=parakeet_available,
        description="Parakeet v3 via onnx-asr",
        platform_ok=True,
        install_hint="" if parakeet_available else get_install_command("onnx-asr"),
        configured=is_parakeet_model,
    ))

    # --- mlx-whisper (Apple Silicon) ---
    mlx_platform = is_apple_silicon()
    mlx_available = False
    if mlx_platform:
        mlx_available = find_spec("mlx_whisper") is not None
    results.append(EngineStatus(
        name="mlx-whisper",
        available=mlx_available,
        description="Whisper on Apple Silicon (MLX)",
        platform_ok=mlx_platform,
        install_hint=(
            "" if mlx_available
            else ("Apple Silicon only" if not mlx_platform
                  else get_install_command("mlx-whisper"))
        ),
        configured=is_whisper_model and mlx_platform and mlx_available,
    ))

    # --- faster-whisper (CTranslate2) ---
    fw_available = find_spec("faster_whisper") is not None
    results.append(EngineStatus(
        name="faster-whisper",
        available=fw_available,
        description="Whisper via CTranslate2",
        platform_ok=True,
        install_hint="" if fw_available else get_install_command("faster-whisper"),
        configured=is_whisper_model and (not mlx_platform or not mlx_available),
    ))

    return [r.to_dict() for r in results]
