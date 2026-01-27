"""Cross-platform hotkey listener using pynput (fallback for macOS/X11)."""

from __future__ import annotations

from collections.abc import Callable

from voxtype.hotkey.base import HotkeyListener

class PynputHotkeyListener(HotkeyListener):
    """Cross-platform hotkey listener using pynput.

    Works on macOS and X11 Linux. Does NOT work on Wayland.
    """

    # Mapping from evdev-style key names to pynput keys
    KEY_MAP = {
        "KEY_SCROLLLOCK": "scroll_lock",
        "KEY_PAUSE": "pause",
        "KEY_F1": "f1",
        "KEY_F2": "f2",
        "KEY_F3": "f3",
        "KEY_F4": "f4",
        "KEY_F5": "f5",
        "KEY_F6": "f6",
        "KEY_F7": "f7",
        "KEY_F8": "f8",
        "KEY_F9": "f9",
        "KEY_F10": "f10",
        "KEY_F11": "f11",
        "KEY_F12": "f12",
        "KEY_RIGHTMETA": "cmd_r",
        "KEY_LEFTMETA": "cmd_l",
        "KEY_RIGHTALT": "alt_r",   # Right Option on Mac
        "KEY_LEFTALT": "alt_l",    # Left Option on Mac
        "KEY_MENU": "menu",
    }

    def __init__(self, key_name: str = "KEY_SCROLLLOCK") -> None:
        """Initialize pynput hotkey listener.

        Args:
            key_name: evdev-style key name (will be mapped to pynput).
        """
        self.key_name = key_name
        self._listener = None
        self._target_key = None
        self._on_press: Callable[[], None] | None = None
        self._on_release: Callable[[], None] | None = None
        self._on_other_key: Callable[[], None] | None = None

    def _get_pynput_key(self):
        """Convert evdev key name to pynput key."""
        from pynput import keyboard

        pynput_name = self.KEY_MAP.get(self.key_name)
        if pynput_name:
            return getattr(keyboard.Key, pynput_name, None)

        # Try direct attribute lookup
        simple_name = self.key_name.lower().replace("key_", "")
        return getattr(keyboard.Key, simple_name, None)

    def _handle_press(self, key) -> None:
        """Handle key press event."""
        if key == self._target_key:
            if self._on_press:
                self._on_press()
        else:
            # Any other key pressed - notify for combo detection
            if self._on_other_key:
                self._on_other_key()

    def _handle_release(self, key) -> None:
        """Handle key release event."""
        if key == self._target_key and self._on_release:
            self._on_release()

    def start(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        on_other_key: Callable[[], None] | None = None,
    ) -> None:
        """Start listening for hotkey events.

        Args:
            on_press: Callback when hotkey is pressed.
            on_release: Callback when hotkey is released.
            on_other_key: Callback when any OTHER key is pressed (for combo detection).
        """
        from pynput import keyboard

        self._target_key = self._get_pynput_key()
        if self._target_key is None:
            raise ValueError(f"Unknown key for pynput: {self.key_name}")

        self._on_press = on_press
        self._on_release = on_release
        self._on_other_key = on_other_key

        self._listener = keyboard.Listener(
            on_press=self._handle_press,
            on_release=self._handle_release,
        )
        self._listener.start()

    def stop(self) -> None:
        """Stop listening for hotkey events."""
        if self._listener:
            self._listener.stop()
            # Wait for listener thread to actually stop (with timeout to avoid hanging)
            try:
                self._listener.join(timeout=2.0)
            except Exception:
                pass
            self._listener = None

        self._on_press = None
        self._on_release = None
        self._on_other_key = None

    def is_key_available(self) -> bool:
        """Check if the configured key is available."""
        return self._get_pynput_key() is not None

    def get_key_name(self) -> str:
        """Get human-readable name of the configured key."""
        name = self.key_name
        if name.startswith("KEY_"):
            name = name[4:]
        return name.replace("_", " ").title()
