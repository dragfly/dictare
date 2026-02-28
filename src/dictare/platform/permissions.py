"""macOS permission checks for Dictare.

Accessibility is always reported as True — not needed for the current
architecture (the Swift launcher handles CGEventTap, not Python).

Input Monitoring permission is checked via the status file written by the Swift
launcher. Runtime hotkey health is tracked separately by the serve process.

Microphone is checked via the native Dictare.app launcher binary, which IS
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
    """Find the Dictare launcher binary.

    Priority order matters: we must use the binary that is registered in the
    macOS TCC database (the one the user granted Accessibility permission to).
    The service-installed bundle (~/Applications) is the one in TCC, so it is
    checked first. The brew Cellar path is a different TCC identity and may
    report false negatives when called from within a launchd service context.
    """
    from dictare.daemon.app_bundle import get_executable_path

    # 1. Use the service-installed bundle (the one registered in TCC)
    service_path = get_executable_path()
    if service_path and __import__("os").path.exists(service_path):
        return service_path

    # 2. Check /Applications (system-wide install)
    from pathlib import Path

    sys_path = Path("/Applications/Dictare.app/Contents/MacOS/Dictare")
    if sys_path.exists():
        return str(sys_path)

    # 3. Brew Cellar fallback (different TCC identity — may return false negatives)
    brew_path = Path("/opt/homebrew/opt/dictare/Dictare.app/Contents/MacOS/Dictare")
    if brew_path.exists():
        return str(brew_path)

    return None


def _check_mic_via_launcher() -> bool:
    """Check microphone permission via the native Dictare.app launcher.

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

    The Swift launcher writes ~/.dictare/hotkey_status after attempting to
    create the CGEventTap.  "active"/"confirmed" mean permission is granted.
    Missing file means unknown, treated as granted for permission UI purposes.
    """
    from pathlib import Path

    status_file = Path.home() / ".dictare" / "hotkey_status"
    try:
        content = status_file.read_text().strip()
        return content in ("active", "confirmed")
    except FileNotFoundError:
        return True


def _check_via_launcher() -> dict[str, bool]:
    """Assemble the permissions dict via the Dictare.app launcher subprocess.

    Calls `Dictare --check-permissions` once to get accessibility + microphone
    (AXIsProcessTrusted + AVCaptureDevice — reliable when called as the app's
    own subprocess, unlike CGPreflightListenEventAccess).
    Input Monitoring is checked via the hotkey_status file written by Swift.
    """
    launcher = _find_launcher()
    if launcher:
        try:
            result = subprocess.run(
                [launcher, "--check-permissions"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout.strip())
                return {
                    "accessibility": data.get("accessibility", True),
                    "microphone": data.get("microphone", True),
                    "input_monitoring": _check_input_monitoring(),
                }
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            logger.warning("Launcher permissions check failed: %s", e)
    return _check_fallback()


def _check_fallback() -> dict[str, bool]:
    """Full Python-only fallback (used when launcher is unavailable)."""
    return {
        "accessibility": True,
        "microphone": _check_mic_fallback(),
        "input_monitoring": _check_input_monitoring(),
    }
