"""macOS Microphone permission checks.

Provides cached checks for AVCaptureDevice authorization, used by:
- Engine /status endpoint (reports permission state)
- Tray app (shows warning if not granted)
"""

from __future__ import annotations

import logging
import sys
import time

logger = logging.getLogger(__name__)

MICROPHONE_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
)

# Cache to avoid repeated system calls (polling hits this every 500ms)
_cache_result: bool | None = None
_cache_time: float = 0.0
_CACHE_TTL = 5.0  # seconds


def is_microphone_granted() -> bool:
    """Check if Microphone permission is granted.

    Returns True on non-macOS platforms.
    Results are cached for 5 seconds.
    """
    if sys.platform != "darwin":
        return True

    global _cache_result, _cache_time  # noqa: PLW0603
    now = time.monotonic()
    if _cache_result is not None and (now - _cache_time) < _CACHE_TTL:
        return _cache_result

    result = _check_mic_authorized()
    _cache_result = result
    _cache_time = now
    return result


def open_microphone_settings() -> None:
    """Open macOS System Settings → Microphone pane."""
    if sys.platform != "darwin":
        return
    import subprocess

    subprocess.Popen(["open", MICROPHONE_SETTINGS_URL])


def _check_mic_authorized() -> bool:
    """Check AVCaptureDevice authorizationStatus for audio via pyobjc.

    Returns True if authorized or if check fails (fail-open).

    AVAuthorizationStatus values:
        0 = notDetermined (never asked — launcher should prompt)
        1 = restricted (parental controls etc.)
        2 = denied (user denied)
        3 = authorized
    """
    try:
        import ctypes

        # Load AVFoundation so its Objective-C classes become available
        ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/AVFoundation.framework/AVFoundation"
        )

        import objc  # pyobjc-core (bundled with pyobjc-framework-Quartz)

        av_capture_device = objc.lookUpClass("AVCaptureDevice")
        # AVMediaTypeAudio = "soun"
        status = av_capture_device.authorizationStatusForMediaType_("soun")
        return status == 3  # .authorized
    except Exception:
        logger.warning("Could not check Microphone permission", exc_info=True)
        return True  # Fail-open: don't block on check failure
