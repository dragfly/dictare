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
        except (subprocess.SubprocessError, OSError):
            return False

    def _has_non_ascii(self, text: str) -> bool:
        """Check if text contains non-ASCII characters."""
        return any(ord(c) > 127 for c in text)

    def _type_via_clipboard(self, text: str, send_enter: bool) -> bool:
        """Type text by copying to clipboard and pasting (for Unicode support)."""
        try:
            # Copy text to clipboard using pbcopy
            proc = subprocess.run(
                ["pbcopy"],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=5,
            )
            if proc.returncode != 0:
                return False

            # Paste with Cmd+V (and optionally Enter)
            if send_enter:
                script = 'tell application "System Events"\nkeystroke "v" using command down\ndelay 0.1\nkey code 36\nend tell'
            else:
                script = 'tell application "System Events" to keystroke "v" using command down'

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def type_text(self, text: str, delay_ms: int = 0, auto_enter: bool = True) -> bool:
        """Type text using AppleScript keystroke command.

        Args:
            text: Text to type.
            delay_ms: Delay between characters in milliseconds.
            auto_enter: If True and text ends with \\n, press Enter key.
                        If False, type literal newline.

        Returns:
            True if successful.
        """
        # Handle newline based on auto_enter mode
        has_newline = text.endswith("\n")
        send_enter = has_newline and auto_enter
        if send_enter:
            text = text[:-1]
        # If auto_enter=False, keep the \n for visual newline

        # Use clipboard for Unicode characters (keystroke doesn't handle them well)
        if self._has_non_ascii(text):
            return self._type_via_clipboard(text, send_enter)

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
        except (subprocess.SubprocessError, OSError):
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "macos-osascript"

    def send_newline(self) -> bool:
        """Send visual newline using Option+Return."""
        try:
            # key code 36 = Return, using option down = Option+Return
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to key code 36 using option down',
                ],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def send_submit(self) -> bool:
        """Send Return key to submit."""
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to key code 36',
                ],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False
