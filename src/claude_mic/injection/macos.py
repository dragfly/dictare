"""macOS text injection using osascript."""

from __future__ import annotations

import subprocess
import sys

from claude_mic.injection.base import TextInjector


class MacOSInjector(TextInjector):
    """macOS text injection using AppleScript.

    Uses osascript to simulate keyboard input.
    Requires Accessibility permissions in System Preferences.
    """

    def __init__(self) -> None:
        """Initialize macOS injector."""
        if sys.platform != "darwin":
            raise RuntimeError("MacOSInjector only works on macOS")

    def is_available(self) -> bool:
        """Check if osascript is available."""
        try:
            result = subprocess.run(
                ["osascript", "-e", "return"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def type_text(self, text: str, delay_ms: int = 0) -> bool:
        """Type text using AppleScript keystroke command.

        Args:
            text: Text to type.
            delay_ms: Delay between characters (not used, AppleScript handles timing).

        Returns:
            True if successful.
        """
        # Escape special characters for AppleScript
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')

        # AppleScript to type text
        script = f'tell application "System Events" to keystroke "{escaped}"'

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "macos-osascript"
