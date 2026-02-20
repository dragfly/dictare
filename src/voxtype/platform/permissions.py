"""macOS permission checks for Voxtype.

Accessibility is always reported as True — not needed for the current
architecture (the Swift launcher handles CGEventTap, not Python).

Input Monitoring is checked via a status file written by the Swift launcher.
The launcher writes ~/.voxtype/hotkey_status ("active" or "failed") after
attempting to create the CGEventTap.  If the file is missing, we assume OK
(engine running from terminal, where pynput handles the hotkey directly).

Microphone is checked via the native Voxtype.app launcher binary, which IS
the process registered with AVFoundation in the TCC database.

Results are cached for 5 seconds (polling interval is 500ms).
"""

from __future__ import annotations

import ctypes
import json
import logging
import subprocess
import sys
import time

logger = logging.getLogger(__name__)

ACCESSIBILITY_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)
MICROPHONE_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
)
INPUT_MONITORING_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
)

# Cache: {"accessibility": bool, "microphone": bool}
_cache: dict[str, bool] | None = None
_cache_time: float = 0.0
_CACHE_TTL = 5.0  # seconds

def get_permissions() -> dict[str, bool]:
    """Get all permission statuses.

    Returns dict with "accessibility", "microphone", and "input_monitoring" booleans.
    On non-macOS, returns all True. Cached for 5 seconds.
    """
    if sys.platform != "darwin":
        return {"accessibility": True, "microphone": True, "input_monitoring": True}

    global _cache, _cache_time  # noqa: PLW0603
    now = time.monotonic()
    if _cache is not None and (now - _cache_time) < _CACHE_TTL:
        return _cache

    result = _check_via_launcher()
    _cache = result
    _cache_time = now
    return result

def is_accessibility_granted() -> bool:
    """Check if Accessibility permission is granted."""
    return get_permissions().get("accessibility", True)

def is_microphone_granted() -> bool:
    """Check if Microphone permission is granted."""
    return get_permissions().get("microphone", True)

def open_accessibility_settings() -> None:
    """Open macOS System Settings → Accessibility pane."""
    if sys.platform != "darwin":
        return
    subprocess.Popen(["open", ACCESSIBILITY_SETTINGS_URL])

def open_microphone_settings() -> None:
    """Open macOS System Settings → Microphone pane."""
    if sys.platform != "darwin":
        return
    subprocess.Popen(["open", MICROPHONE_SETTINGS_URL])

def is_input_monitoring_granted() -> bool:
    """Check if Input Monitoring permission is granted."""
    return get_permissions().get("input_monitoring", True)

def open_input_monitoring_settings() -> None:
    """Open macOS System Settings → Input Monitoring pane."""
    if sys.platform != "darwin":
        return
    subprocess.Popen(["open", INPUT_MONITORING_SETTINGS_URL])

def _find_launcher() -> str | None:
    """Find the Voxtype launcher binary.

    Priority order matters: we must use the binary that is registered in the
    macOS TCC database (the one the user granted Accessibility permission to).
    The service-installed bundle (~/Applications) is the one in TCC, so it is
    checked first. The brew Cellar path is a different TCC identity and may
    report false negatives when called from within a launchd service context.
    """
    from voxtype.daemon.app_bundle import get_executable_path

    # 1. Use the service-installed bundle (the one registered in TCC)
    service_path = get_executable_path()
    if service_path and __import__("os").path.exists(service_path):
        return service_path

    # 2. Check /Applications (system-wide install)
    from pathlib import Path

    sys_path = Path("/Applications/Voxtype.app/Contents/MacOS/Voxtype")
    if sys_path.exists():
        return str(sys_path)

    # 3. Brew Cellar fallback (different TCC identity — may return false negatives)
    brew_path = Path("/opt/homebrew/opt/voxtype/Voxtype.app/Contents/MacOS/Voxtype")
    if brew_path.exists():
        return str(brew_path)

    return None

def _check_mic_via_launcher() -> bool:
    """Check microphone permission via the native Voxtype.app launcher.

    The launcher binary registered with AVFoundation, so it is the correct
    process to query for microphone status.  Falls back to True on failure.
    """
    launcher = _find_launcher()
    if not launcher:
        return _check_mic_fallback()
    try:
        result = subprocess.run(
            [launcher, "--check-permissions"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return json.loads(result.stdout.strip()).get("microphone", True)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        logger.warning("Launcher mic check failed: %s", e)
    return _check_mic_fallback()

def _check_mic_fallback() -> bool:
    """Check microphone permission from Python via objc (fallback)."""
    try:
        ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/AVFoundation.framework/AVFoundation"
        )
        import objc

        av_device = objc.lookUpClass("AVCaptureDevice")
        status = av_device.authorizationStatusForMediaType_("soun")
        return status == 3
    except Exception:
        return True

def _check_input_monitoring() -> bool:
    """Check Input Monitoring by reading the launcher's hotkey_status file.

    The Swift launcher writes ~/.voxtype/hotkey_status after attempting to
    create the CGEventTap.  "active" = granted, "failed" = not granted.
    Missing file = assume OK (terminal mode, or launcher hasn't run yet).
    """
    from pathlib import Path

    status_file = Path.home() / ".voxtype" / "hotkey_status"
    try:
        content = status_file.read_text().strip()
        return content == "active"
    except FileNotFoundError:
        return True  # No status file = running from terminal, assume OK

def _check_via_launcher() -> dict[str, bool]:
    """Assemble the permissions dict.

    Accessibility is always True — not checkable from launchd (see module
    docstring). Microphone is checked via the Voxtype.app launcher subprocess.
    Input Monitoring is checked via the hotkey_status file written by Swift.
    """
    return {
        "accessibility": True,
        "microphone": _check_mic_via_launcher(),
        "input_monitoring": _check_input_monitoring(),
    }

def _check_fallback() -> dict[str, bool]:
    """Full Python-only fallback (used when launcher is unavailable)."""
    return {
        "accessibility": True,
        "microphone": _check_mic_fallback(),
        "input_monitoring": _check_input_monitoring(),
    }
