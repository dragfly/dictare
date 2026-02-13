"""macOS permission checks via the native Voxtype launcher binary.

The launcher binary (Voxtype.app/Contents/MacOS/Voxtype) IS the trusted process
in TCC (Accessibility, Microphone). Checking from Python gives false negatives
because Python is a different binary. So we shell out to the launcher with
--check-permissions and parse its JSON output.

Results are cached for 5 seconds (polling interval is 500ms).
"""

from __future__ import annotations

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

# Cache: {"accessibility": bool, "microphone": bool}
_cache: dict[str, bool] | None = None
_cache_time: float = 0.0
_CACHE_TTL = 5.0  # seconds

def get_permissions() -> dict[str, bool]:
    """Get all permission statuses.

    Returns dict with "accessibility" and "microphone" booleans.
    On non-macOS, returns all True. Cached for 5 seconds.
    """
    if sys.platform != "darwin":
        return {"accessibility": True, "microphone": True}

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

def _find_launcher() -> str | None:
    """Find the Voxtype launcher binary."""
    from pathlib import Path

    # Check brew Cellar (opt_prefix symlink)
    brew_path = Path("/opt/homebrew/opt/voxtype/Voxtype.app/Contents/MacOS/Voxtype")
    if brew_path.exists():
        return str(brew_path)

    # Check ~/Applications
    home_path = Path.home() / "Applications/Voxtype.app/Contents/MacOS/Voxtype"
    if home_path.exists():
        return str(home_path)

    # Check /Applications
    sys_path = Path("/Applications/Voxtype.app/Contents/MacOS/Voxtype")
    if sys_path.exists():
        return str(sys_path)

    return None

def _check_via_launcher() -> dict[str, bool]:
    """Call the native launcher with --check-permissions."""
    launcher = _find_launcher()
    if not launcher:
        # No launcher found — fall back to Python-level checks
        return _check_fallback()

    try:
        result = subprocess.run(
            [launcher, "--check-permissions"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        logger.warning("Launcher permission check failed: %s", e)

    return _check_fallback()

def _check_fallback() -> dict[str, bool]:
    """Fallback: check permissions from Python (may give false negatives)."""
    accessibility = True
    microphone = True

    try:
        import ctypes

        as_lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        as_lib.AXIsProcessTrusted.restype = ctypes.c_bool
        accessibility = bool(as_lib.AXIsProcessTrusted())
    except Exception:
        pass

    try:
        import ctypes

        ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/AVFoundation.framework/AVFoundation"
        )
        import objc

        av_device = objc.lookUpClass("AVCaptureDevice")
        status = av_device.authorizationStatusForMediaType_("soun")
        microphone = status == 3
    except Exception:
        pass

    return {"accessibility": accessibility, "microphone": microphone}
