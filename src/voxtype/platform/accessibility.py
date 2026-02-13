"""macOS Accessibility permission checks.

Provides cached checks for AXIsProcessTrusted, used by:
- Engine /status endpoint (reports permission state)
- Tray app (shows warning if not granted)
- CLI setup (prompts user during initial setup)
"""

from __future__ import annotations

import logging
import sys
import time

logger = logging.getLogger(__name__)

# macOS System Settings URL for Accessibility pane
ACCESSIBILITY_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)

# Cache to avoid repeated system calls (polling hits this every 500ms)
_cache_result: bool | None = None
_cache_time: float = 0.0
_CACHE_TTL = 5.0  # seconds

def is_accessibility_granted() -> bool:
    """Check if Accessibility permission is granted (no prompt).

    Returns True on non-macOS platforms.
    Results are cached for 5 seconds.
    """
    if sys.platform != "darwin":
        return True

    global _cache_result, _cache_time  # noqa: PLW0603
    now = time.monotonic()
    if _cache_result is not None and (now - _cache_time) < _CACHE_TTL:
        return _cache_result

    result = _check_ax_trusted(prompt=False)
    _cache_result = result
    _cache_time = now
    return result

def request_accessibility() -> bool:
    """Check Accessibility permission and prompt the macOS system dialog if needed.

    Returns True if the process is trusted, False otherwise.
    Returns True on non-macOS platforms.
    Invalidates the cache so the next is_accessibility_granted() call re-checks.
    """
    if sys.platform != "darwin":
        return True

    global _cache_result, _cache_time  # noqa: PLW0603
    result = _check_ax_trusted(prompt=True)
    # Invalidate cache so polling picks up the new state
    _cache_result = result
    _cache_time = time.monotonic()
    return result

def open_accessibility_settings() -> None:
    """Open macOS System Settings → Accessibility pane."""
    if sys.platform != "darwin":
        return
    import subprocess

    subprocess.Popen(["open", ACCESSIBILITY_SETTINGS_URL])

def _check_ax_trusted(prompt: bool) -> bool:
    """Call AXIsProcessTrustedWithOptions via ctypes.

    Args:
        prompt: If True, macOS shows the "grant accessibility" dialog.
    """
    try:
        import ctypes

        as_path = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        cf_path = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"

        appserv = ctypes.cdll.LoadLibrary(as_path)
        cf = ctypes.cdll.LoadLibrary(cf_path)

        prompt_key = ctypes.c_void_p.in_dll(
            appserv, "kAXTrustedCheckOptionPrompt"
        )

        cf.CFDictionaryCreateMutable.restype = ctypes.c_void_p
        cf.CFDictionaryCreateMutable.argtypes = [
            ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
        ]
        options = cf.CFDictionaryCreateMutable(None, 1, None, None)

        cf.CFDictionarySetValue.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]

        if prompt:
            cf_true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
            cf.CFDictionarySetValue(options, prompt_key, cf_true)
        else:
            cf_false = ctypes.c_void_p.in_dll(cf, "kCFBooleanFalse")
            cf.CFDictionarySetValue(options, prompt_key, cf_false)

        appserv.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        appserv.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
        trusted = appserv.AXIsProcessTrustedWithOptions(options)

        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease(options)

        return bool(trusted)
    except Exception:
        logger.warning("Could not check Accessibility permission", exc_info=True)
        return False
