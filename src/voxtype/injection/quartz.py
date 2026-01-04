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
        except OSError:
            self._available = False
            return False

    def type_text(self, text: str, delay_ms: int = 0, auto_enter: bool = True) -> bool:
        """Type text using Quartz keyboard events.

        Args:
            text: Text to type.
            delay_ms: Delay between characters in milliseconds.
            auto_enter: If True and text ends with \\n, press Enter key.
                        If False, type literal newline.

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

        # Handle newline based on auto_enter mode
        has_newline = text.endswith("\n")
        send_enter = has_newline and auto_enter
        if send_enter:
            text = text[:-1]
        # If auto_enter=False, keep the \n for visual newline

        try:
            source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            if source is None:
                return False

            delay_sec = delay_ms / 1000.0 if delay_ms > 0 else 0

            # Type each character
            for char in text:
                # Key down - this is where the character is typed
                event_down = CGEventCreateKeyboardEvent(source, 0, True)
                CGEventKeyboardSetUnicodeString(event_down, len(char), char)
                CGEventPost(kCGSessionEventTap, event_down)

                # Key up - just release, no character
                event_up = CGEventCreateKeyboardEvent(source, 0, False)
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
        except (ImportError, OSError):
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "macos-quartz"

    def send_newline(self) -> bool:
        """Send visual newline using Option+Return."""
        try:
            from Quartz import (
                CGEventCreateKeyboardEvent,
                CGEventPost,
                CGEventSetFlags,
                CGEventSourceCreate,
                kCGEventFlagMaskAlternate,
                kCGEventSourceStateHIDSystemState,
                kCGSessionEventTap,
            )
        except ImportError:
            return False

        try:
            source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            if source is None:
                return False

            # Key code 36 = Return with Option modifier
            event_down = CGEventCreateKeyboardEvent(source, 36, True)
            CGEventSetFlags(event_down, kCGEventFlagMaskAlternate)
            CGEventPost(kCGSessionEventTap, event_down)

            event_up = CGEventCreateKeyboardEvent(source, 36, False)
            CGEventPost(kCGSessionEventTap, event_up)

            return True
        except (ImportError, OSError):
            return False

    def send_submit(self) -> bool:
        """Send Return key to submit."""
        try:
            from Quartz import (
                CGEventCreateKeyboardEvent,
                CGEventPost,
                CGEventSourceCreate,
                kCGEventSourceStateHIDSystemState,
                kCGSessionEventTap,
            )
        except ImportError:
            return False

        try:
            source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            if source is None:
                return False

            # Key code 36 = Return
            event_down = CGEventCreateKeyboardEvent(source, 36, True)
            CGEventPost(kCGSessionEventTap, event_down)

            event_up = CGEventCreateKeyboardEvent(source, 36, False)
            CGEventPost(kCGSessionEventTap, event_up)

            return True
        except (ImportError, OSError):
            return False
