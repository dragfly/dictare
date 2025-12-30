"""Text injection using ydotool."""

from __future__ import annotations

import shutil
import subprocess

from claude_mic.injection.base import TextInjector

class YdotoolInjector(TextInjector):
    """Text injection using ydotool.

    Works on X11, Wayland, and console.
    Requires ydotoold daemon to be running.
    """

    def __init__(self) -> None:
        """Initialize ydotool injector."""
        self._ydotool_path: str | None = None

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

    def type_text(self, text: str, delay_ms: int = 0) -> bool:
        """Type text using ydotool.

        Args:
            text: Text to type. If ends with newline, sends Enter key.
            delay_ms: Delay between characters in milliseconds.

        Returns:
            True if successful.
        """
        if not self._ydotool_path:
            self._ydotool_path = shutil.which("ydotool")
            if not self._ydotool_path:
                return False

        # Check if we need to send Enter at the end
        send_enter = text.endswith("\n")
        if send_enter:
            text = text.rstrip("\n")

        try:
            # Type the text
            cmd = [self._ydotool_path, "type"]
            # Override ydotool's slow defaults (20ms each)
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

            # Send Enter key if needed (ydotool type doesn't interpret \n)
            if send_enter:
                enter_result = subprocess.run(
                    [self._ydotool_path, "key", "enter"],
                    capture_output=True,
                    timeout=5,
                )
                return enter_result.returncode == 0

            return True
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "ydotool"
