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

    def type_text(self, text: str, delay_ms: int = 0) -> bool:
        """Type text using xdotool.

        Args:
            text: Text to type.
            delay_ms: Delay between characters in milliseconds.

        Returns:
            True if successful.
        """
        if not self._xdotool_path:
            self._xdotool_path = shutil.which("xdotool")
            if not self._xdotool_path:
                return False

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
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "xdotool"
