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
    def type_text(self, text: str, delay_ms: int = 0, auto_enter: bool = True) -> bool:
        """Type text into the active window.

        Args:
            text: Text to type. If ends with newline, behavior depends on auto_enter.
            delay_ms: Delay between characters in milliseconds.
            auto_enter: If True and text ends with \\n, press Enter key (submit).
                        If False and text ends with \\n, type literal newline (visual only).

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

    def send_newline(self) -> bool:
        """Send a visual newline (line break without submit).

        This creates a new line in the text input without sending/submitting.
        Implementation varies by backend:
        - Keyboard (ydotool): Alt+Enter
        - File: \n written to file

        Returns:
            True if successful.
        """
        # Default: not supported
        return False

    def send_submit(self) -> bool:
        """Send submit/enter (send the text).

        This submits/sends the current text input.
        Implementation varies by backend:
        - Keyboard: Enter key
        - Clipboard: Enter key after paste
        - File: special marker or no-op

        Returns:
            True if successful.
        """
        # Default: not supported
        return False
