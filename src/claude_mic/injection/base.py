"""Abstract base class for text injection."""

from __future__ import annotations

from abc import ABC, abstractmethod


class TextInjector(ABC):
    """Abstract base class for text injection."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this injector is available on the system.

        Returns:
            True if the injector can be used.
        """
        pass

    @abstractmethod
    def type_text(self, text: str, delay_ms: int = 0) -> bool:
        """Type text into the active window.

        Args:
            text: Text to type.
            delay_ms: Delay between characters in milliseconds.

        Returns:
            True if successful.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the name of this injector.

        Returns:
            Human-readable injector name.
        """
        pass
