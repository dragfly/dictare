"""macOS text injection using osascript."""

from __future__ import annotations

import os
import subprocess
import sys

from voxtype.injection.base import TextInjector

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
        # Check if text ends with newline (Enter requested)
        send_enter = text.endswith("\n")
        if send_enter:
            text = text[:-1]

        # Escape special characters for AppleScript
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')

        # Build AppleScript: type text, then optionally press Return
        if send_enter:
            # Small delay between text and Return to ensure text is fully typed
            script = f'tell application "System Events"\nkeystroke "{escaped}"\ndelay 0.1\nkey code 36\nend tell'
        else:
            script = f'tell application "System Events" to keystroke "{escaped}"'

        try:
            # Ensure UTF-8 locale for proper accent handling
            env = os.environ.copy()
            env["LANG"] = "en_US.UTF-8"
            env["LC_ALL"] = "en_US.UTF-8"

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=30,
                encoding="utf-8",
                env=env,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "macos-osascript"
