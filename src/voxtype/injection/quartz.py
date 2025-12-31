"""macOS text injection using Quartz (CoreGraphics) for Unicode support."""

from __future__ import annotations

import sys
import time

from voxtype.injection.base import TextInjector

class QuartzInjector(TextInjector):
    """macOS text injection using Quartz CGEvent.

    Uses CGEventKeyboardSetUnicodeString for full Unicode support.
    Requires Accessibility permissions in System Preferences.
    """

    def __init__(self) -> None:
        """Initialize Quartz injector."""
        if sys.platform != "darwin":
            raise RuntimeError("QuartzInjector only works on macOS")
        self._available: bool | None = None

    def is_available(self) -> bool:
        """Check if Quartz is available."""
        if self._available is not None:
            return self._available

        try:
            from Quartz import (
                CGEventCreateKeyboardEvent,
                CGEventKeyboardSetUnicodeString,
                CGEventPost,
                CGEventSourceCreate,
                kCGEventSourceStateHIDSystemState,
                kCGSessionEventTap,
            )

            # Try to create an event source
            source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            self._available = source is not None
            return self._available
        except ImportError:
            self._available = False
            return False
        except Exception:
            self._available = False
            return False

    def type_text(self, text: str, delay_ms: int = 0) -> bool:
        """Type text using Quartz keyboard events.

        Args:
            text: Text to type.
            delay_ms: Delay between characters in milliseconds.

        Returns:
            True if successful.
        """
        try:
            from Quartz import (
                CGEventCreateKeyboardEvent,
                CGEventKeyboardSetUnicodeString,
                CGEventPost,
                CGEventSourceCreate,
                kCGEventSourceStateHIDSystemState,
                kCGSessionEventTap,
            )
        except ImportError:
            return False

        # Check if text ends with newline (Enter requested)
        send_enter = text.endswith("\n")
        if send_enter:
            text = text[:-1]

        try:
            source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            if source is None:
                return False

            delay_sec = delay_ms / 1000.0 if delay_ms > 0 else 0

            # Type each character
            for char in text:
                # Key down
                event_down = CGEventCreateKeyboardEvent(source, 0, True)
                CGEventKeyboardSetUnicodeString(event_down, len(char), char)
                CGEventPost(kCGSessionEventTap, event_down)

                # Key up
                event_up = CGEventCreateKeyboardEvent(source, 0, False)
                CGEventKeyboardSetUnicodeString(event_up, len(char), char)
                CGEventPost(kCGSessionEventTap, event_up)

                if delay_sec > 0:
                    time.sleep(delay_sec)

            # Send Enter if needed
            if send_enter:
                time.sleep(0.1)
                # Key code 36 = Return
                enter_down = CGEventCreateKeyboardEvent(source, 36, True)
                CGEventPost(kCGSessionEventTap, enter_down)
                enter_up = CGEventCreateKeyboardEvent(source, 36, False)
                CGEventPost(kCGSessionEventTap, enter_up)

            return True
        except Exception:
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "macos-quartz"
