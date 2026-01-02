"""Text injection using xdotool (X11 only)."""

from __future__ import annotations

import shutil
import subprocess

from voxtype.injection.base import TextInjector

class XdotoolInjector(TextInjector):
    """Text injection using xdotool.

    X11 only, does NOT work on Wayland.
    """

    def __init__(self) -> None:
        """Initialize xdotool injector."""
        self._xdotool_path: str | None = None

    def is_available(self) -> bool:
        """Check if xdotool is available and we're on X11."""
        import os

        # xdotool doesn't work on Wayland
        if os.environ.get("WAYLAND_DISPLAY"):
            return False

        # Need DISPLAY for X11
        if not os.environ.get("DISPLAY"):
            return False

        self._xdotool_path = shutil.which("xdotool")
        return self._xdotool_path is not None

    def type_text(self, text: str, delay_ms: int = 0, auto_enter: bool = True) -> bool:
        """Type text using xdotool.

        Args:
            text: Text to type.
            delay_ms: Delay between characters in milliseconds.
            auto_enter: If True and text ends with \\n, press Enter key.
                        If False, type literal newline.

        Returns:
            True if successful.
        """
        if not self._xdotool_path:
            self._xdotool_path = shutil.which("xdotool")
            if not self._xdotool_path:
                return False

        # Handle newline based on auto_enter mode
        has_newline = text.endswith("\n")
        if has_newline and auto_enter:
            text = text[:-1]

        try:
            cmd = [self._xdotool_path, "type"]
            if delay_ms > 0:
                cmd.extend(["--delay", str(delay_ms)])
            cmd.append("--")
            cmd.append(text)

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                return False

            # Send Enter key if auto_enter mode
            if has_newline and auto_enter:
                enter_result = subprocess.run(
                    [self._xdotool_path, "key", "Return"],
                    capture_output=True,
                    timeout=5,
                )
                return enter_result.returncode == 0

            return True
        except subprocess.TimeoutExpired:
            return False
        except (subprocess.SubprocessError, OSError):
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "xdotool"

    def send_newline(self) -> bool:
        """Send visual newline using Alt+Return."""
        if not self._xdotool_path:
            self._xdotool_path = shutil.which("xdotool")
            if not self._xdotool_path:
                return False

        try:
            result = subprocess.run(
                [self._xdotool_path, "key", "alt+Return"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def send_submit(self) -> bool:
        """Send Return key to submit."""
        if not self._xdotool_path:
            self._xdotool_path = shutil.which("xdotool")
            if not self._xdotool_path:
                return False

        try:
            result = subprocess.run(
                [self._xdotool_path, "key", "Return"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False
