"""Text injection using ydotool."""

from __future__ import annotations

import shutil
import subprocess
import time

from voxtype.injection.base import TextInjector, sanitize_text_for_injection

# Key codes for ydotool
KEY_LEFTCTRL = 29
KEY_LEFTSHIFT = 42
KEY_LEFTALT = 56
KEY_ENTER = 28
KEY_U = 22
KEY_SPACE = 57

class YdotoolInjector(TextInjector):
    """Text injection using ydotool.

    Works on X11, Wayland, and console.
    Requires ydotoold daemon to be running.
    Uses Ctrl+Shift+U for Unicode characters (GTK/ibus).
    """

    def __init__(self) -> None:
        """Initialize ydotool injector."""
        self._ydotool_path: str | None = None
        self._enter_sent: bool = False

    def is_available(self) -> bool:
        """Check if ydotool is available and daemon is running."""
        self._ydotool_path = shutil.which("ydotool")
        if not self._ydotool_path:
            return False

        # Check if ydotoold is running
        try:
            result = subprocess.run(
                ["pgrep", "-x", "ydotoold"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _has_non_ascii(self, text: str) -> bool:
        """Check if text contains non-ASCII characters."""
        return any(ord(c) > 127 for c in text)

    def _type_unicode_char(self, char: str) -> bool:
        """Type a single Unicode character using Ctrl+Shift+U method."""
        if not self._ydotool_path:
            return False

        hex_code = format(ord(char), "x")

        try:
            # Press Ctrl+Shift+U
            subprocess.run(
                [self._ydotool_path, "key", f"{KEY_LEFTCTRL}:1", f"{KEY_LEFTSHIFT}:1", f"{KEY_U}:1", f"{KEY_U}:0", f"{KEY_LEFTSHIFT}:0", f"{KEY_LEFTCTRL}:0"],
                capture_output=True,
                timeout=5,
            )
            time.sleep(0.05)

            # Type the hex code
            subprocess.run(
                [self._ydotool_path, "type", "--key-delay", "1", "--key-hold", "1", "--", hex_code],
                capture_output=True,
                timeout=5,
            )
            time.sleep(0.05)

            # Press Space to confirm
            subprocess.run(
                [self._ydotool_path, "key", f"{KEY_SPACE}:1", f"{KEY_SPACE}:0"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (subprocess.SubprocessError, OSError):
            return False

    def type_text(self, text: str, delay_ms: int = 0, auto_enter: bool = True) -> bool:
        """Type text using ydotool.

        Args:
            text: Text to type (without trailing newline).
            delay_ms: Delay between characters in milliseconds.
            auto_enter: If True, press Enter after text (submit).
                        If False, press Shift+Enter (visual newline).

        Returns:
            True if successful.
        """
        if not self._ydotool_path:
            self._ydotool_path = shutil.which("ydotool")
            if not self._ydotool_path:
                return False

        # Sanitize text to remove any escape sequences or control characters
        text = sanitize_text_for_injection(text)

        delay_sec = delay_ms / 1000.0 if delay_ms > 0 else 0

        try:
            # If text has Unicode, type character by character
            if self._has_non_ascii(text):
                for char in text:
                    if ord(char) > 127:
                        # Unicode: use Ctrl+Shift+U method
                        if not self._type_unicode_char(char):
                            return False
                    else:
                        # ASCII: use normal type
                        result = subprocess.run(
                            [self._ydotool_path, "type", "--key-delay", "1", "--key-hold", "1", "--", char],
                            capture_output=True,
                            timeout=5,
                        )
                        if result.returncode != 0:
                            return False
                    if delay_sec > 0:
                        time.sleep(delay_sec)
            else:
                # Pure ASCII: type all at once (faster)
                cmd = [self._ydotool_path, "type"]
                cmd.extend(["--key-delay", str(delay_ms) if delay_ms > 0 else "1"])
                cmd.extend(["--key-hold", "1"])
                cmd.append("--")
                cmd.append(text)

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    return False

            # Send terminator
            time.sleep(0.2)
            if auto_enter:
                # Enter key (submit)
                enter_result = subprocess.run(
                    [self._ydotool_path, "key", f"{KEY_ENTER}:1", f"{KEY_ENTER}:0"],
                    capture_output=True,
                    timeout=5,
                )
                if enter_result.returncode != 0:
                    return False
                self._enter_sent = True
            else:
                # Shift+Enter (visual newline)
                shift_enter_result = subprocess.run(
                    [
                        self._ydotool_path,
                        "key",
                        f"{KEY_LEFTSHIFT}:1",
                        f"{KEY_ENTER}:1",
                        f"{KEY_ENTER}:0",
                        f"{KEY_LEFTSHIFT}:0",
                    ],
                    capture_output=True,
                    timeout=5,
                )
                if shift_enter_result.returncode != 0:
                    return False
                self._enter_sent = False

            return True
        except subprocess.TimeoutExpired:
            return False
        except (subprocess.SubprocessError, OSError):
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "ydotool"

    def send_newline(self) -> bool:
        """Send visual newline using Shift+Enter.

        Shift+Enter is interpreted as newline-without-submit in most apps.
        """
        if not self._ydotool_path:
            self._ydotool_path = shutil.which("ydotool")
            if not self._ydotool_path:
                return False

        try:
            # Shift+Enter: Shift down, Enter down, Enter up, Shift up
            result = subprocess.run(
                [
                    self._ydotool_path,
                    "key",
                    f"{KEY_LEFTSHIFT}:1",
                    f"{KEY_ENTER}:1",
                    f"{KEY_ENTER}:0",
                    f"{KEY_LEFTSHIFT}:0",
                ],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def send_submit(self) -> bool:
        """Send Enter key to submit."""
        if not self._ydotool_path:
            self._ydotool_path = shutil.which("ydotool")
            if not self._ydotool_path:
                return False

        try:
            result = subprocess.run(
                [self._ydotool_path, "key", f"{KEY_ENTER}:1", f"{KEY_ENTER}:0"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False
