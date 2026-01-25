"""Abstract base class for text injection."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod


def sanitize_text_for_injection(text: str) -> str:
    """Remove ANSI escape sequences and control characters from text.

    This prevents terminal escape sequences like [27;2;13~ from being
    injected as text, which can happen with certain terminal emulators
    or text sources.

    Args:
        text: Text that may contain escape sequences.

    Returns:
        Cleaned text with only printable characters and common whitespace.
    """
    # Remove ANSI escape sequences (ESC [ ... or ESC followed by other sequences)
    # Pattern matches: ESC [ ... (CSI sequences), ESC ] ... (OSC), etc.
    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)  # CSI sequences
    text = re.sub(r'\x1b\][^\x07]*\x07', '', text)     # OSC sequences ending with BEL
    text = re.sub(r'\x1b\][^\x1b]*\x1b\\', '', text)   # OSC sequences ending with ST
    text = re.sub(r'\x1b[^[]', '', text)               # Other ESC sequences

    # Remove other common terminal control sequences
    # Pattern for bracketed paste mode and similar: [numbers~
    text = re.sub(r'\[[0-9;]+~', '', text)

    # Remove all control characters except common whitespace (tab, newline, carriage return)
    # Keep: \t (09), \n (0A), \r (0D), space and printable chars
    text = ''.join(
        char for char in text
        if char in ('\t', '\n', '\r') or (ord(char) >= 32 and ord(char) != 127)
    )

    return text


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
    def type_text(
        self,
        text: str,
        delay_ms: int = 0,
        auto_enter: bool = True,
        submit_keys: str = "enter",
        newline_keys: str = "alt+enter",
    ) -> bool:
        """Type text into the active window.

        Args:
            text: Text to type. If ends with newline, behavior depends on auto_enter.
            delay_ms: Delay between characters in milliseconds.
            auto_enter: If True, send submit_keys after text. If False, send newline_keys.
            submit_keys: Key combination for submit (e.g., "enter").
            newline_keys: Key combination for visual newline (e.g., "alt+enter", "shift+enter").

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
