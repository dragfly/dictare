"""macOS text injection using Quartz (CoreGraphics) for Unicode support."""

from __future__ import annotations

import sys
import time

from dictare.agent.injection.base import TextInjector, sanitize_text_for_injection

# macOS virtual key codes
MACOS_KEY_CODES = {
    "enter": 36,
    "return": 36,
    "shift": None,  # Modifier, not a key code
    "alt": None,    # Modifier, not a key code
    "option": None, # Modifier, not a key code
    "ctrl": None,   # Modifier, not a key code
    "command": None,  # Modifier, not a key code
    "cmd": None,    # Modifier, not a key code
}


def parse_macos_key_combo(combo: str) -> tuple[int | None, int]:
    """Parse a key combination for macOS.

    Args:
        combo: Key combination string (e.g., "enter", "shift+enter", "alt+enter")

    Returns:
        Tuple of (modifier_flags, key_code). modifier_flags is a bitmask or 0.
    """
    try:
        from Quartz import (
            kCGEventFlagMaskAlternate,
            kCGEventFlagMaskCommand,
            kCGEventFlagMaskControl,
            kCGEventFlagMaskShift,
        )
    except ImportError:
        return (0, 36)  # Default to Enter with no modifiers

    keys = [k.strip().lower() for k in combo.split("+")]
    flags = 0
    key_code = 36  # Default to Enter

    for key in keys:
        if key in ("shift",):
            flags |= kCGEventFlagMaskShift
        elif key in ("alt", "option"):
            flags |= kCGEventFlagMaskAlternate
        elif key in ("ctrl", "control"):
            flags |= kCGEventFlagMaskControl
        elif key in ("cmd", "command"):
            flags |= kCGEventFlagMaskCommand
        elif key in ("enter", "return"):
            key_code = 36
        # Add more keys as needed

    return (flags, key_code)


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
            from Quartz import (  # noqa: F401
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

    def type_text(
        self,
        text: str,
        delay_ms: int = 0,
        auto_enter: bool = True,
        submit_keys: str = "enter",
        newline_keys: str = "shift+enter",
    ) -> bool:
        """Type text using Quartz keyboard events.

        Args:
            text: Text to type (without trailing newline).
            delay_ms: Delay between characters in milliseconds.
            auto_enter: If True, send submit_keys. If False, send newline_keys.
            submit_keys: Key combination for submit (e.g., "enter").
            newline_keys: Key combination for visual newline (e.g., "shift+enter").

        Returns:
            True if successful.
        """
        try:
            from Quartz import (
                CGEventCreateKeyboardEvent,
                CGEventKeyboardSetUnicodeString,
                CGEventPost,
                CGEventSetFlags,
                CGEventSourceCreate,
                kCGEventSourceStateHIDSystemState,
                kCGSessionEventTap,
            )
        except ImportError:
            return False

        # Sanitize text to remove any escape sequences or control characters
        # that might have been captured (e.g., from terminal emulators like Ghostty)
        text = sanitize_text_for_injection(text)

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

            # Send terminator using configurable keys
            time.sleep(0.1)
            keys_to_send = submit_keys if auto_enter else newline_keys
            flags, key_code = parse_macos_key_combo(keys_to_send)

            event_down = CGEventCreateKeyboardEvent(source, key_code, True)
            if flags:
                CGEventSetFlags(event_down, flags)
            CGEventPost(kCGSessionEventTap, event_down)
            event_up = CGEventCreateKeyboardEvent(source, key_code, False)
            CGEventPost(kCGSessionEventTap, event_up)

            return True
        except (ImportError, OSError):
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "macos-quartz"

    def send_newline(self) -> bool:
        """Send visual newline using Shift+Return.

        Shift+Return is the standard "newline without submit" in most apps:
        - Chat apps (Slack, Discord, Teams): newline ✓
        - LLM UIs (ChatGPT, Claude web): newline ✓
        - Editors (VSCode, etc.): newline ✓
        - iTerm2, Terminal.app: newline ✓

        Known limitations:
        - Ghostty: requires keybind config, and even then programmatic
          injection may not trigger it. See ISSUE_NEWLINE_ESCAPE.md
        - Terminals with Option=Meta: may generate ESC prefix

        For terminal prompt use, newline and submit are effectively the same
        (both execute the command), so this distinction mainly matters for
        chat apps and editors.
        """
        try:
            from Quartz import (
                CGEventCreateKeyboardEvent,
                CGEventPost,
                CGEventSetFlags,
                CGEventSourceCreate,
                kCGEventFlagMaskShift,
                kCGEventSourceStateHIDSystemState,
                kCGSessionEventTap,
            )
        except ImportError:
            return False

        try:
            source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            if source is None:
                return False

            # Shift+Return (keycode 36 with Shift modifier)
            event_down = CGEventCreateKeyboardEvent(source, 36, True)
            CGEventSetFlags(event_down, kCGEventFlagMaskShift)
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
