"""Abstract base class for hotkey listeners."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class HotkeyListener(ABC):
    """Abstract base class for hotkey listeners."""

    @abstractmethod
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
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop listening for hotkey events."""
        pass

    @abstractmethod
    def is_key_available(self) -> bool:
        """Check if the configured key is available on any keyboard.

        Returns:
            True if the key is available.
        """
        pass

    @abstractmethod
    def get_key_name(self) -> str:
        """Get human-readable name of the configured key.

        Returns:
            Key name string.
        """
        pass

    def capture_next_key(self, timeout: float = 10.0) -> str | None:
        """Capture the next physical key press and return its evdev name.

        Blocks until a key is pressed or timeout expires.
        Returns None if the listener is not running or timed out.
        """
        return None
