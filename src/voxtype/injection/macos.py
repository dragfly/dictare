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
            delay_ms: Delay between characters in milliseconds.

        Returns:
            True if successful.
        """
        # Check if text ends with newline (Enter requested)
        send_enter = text.endswith("\n")
        if send_enter:
            text = text[:-1]

        # Escape special characters for AppleScript
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')

        # Build AppleScript
        if delay_ms > 0:
            # Type character by character with delay (slower but safer for some apps)
            delay_sec = delay_ms / 1000.0
            lines = [f'set theText to "{escaped}"']
            lines.append("tell application \"System Events\"")
            lines.append("repeat with theChar in characters of theText")
            lines.append("keystroke theChar")
            lines.append(f"delay {delay_sec}")
            lines.append("end repeat")
            if send_enter:
                lines.append("delay 0.1")
                lines.append("key code 36")
            lines.append("end tell")
            script = "\n".join(lines)
        else:
            # Fast bulk typing
            if send_enter:
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
                timeout=120,  # Longer timeout for slow typing
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
