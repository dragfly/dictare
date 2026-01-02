"""Text injection using wtype (Wayland only)."""

from __future__ import annotations

import shutil
import subprocess

from voxtype.injection.base import TextInjector


class WtypeInjector(TextInjector):
    """Text injection using wtype.

    Wayland-only, uses the virtual-keyboard protocol.
    """

    def __init__(self) -> None:
        """Initialize wtype injector."""
        self._wtype_path: str | None = None

    def is_available(self) -> bool:
        """Check if wtype is available and we're on Wayland."""
        import os

        # wtype only works on Wayland
        if not os.environ.get("WAYLAND_DISPLAY"):
            return False

        self._wtype_path = shutil.which("wtype")
        return self._wtype_path is not None

    def type_text(self, text: str, delay_ms: int = 0, auto_enter: bool = True) -> bool:
        """Type text using wtype.

        Args:
            text: Text to type.
            delay_ms: Delay between characters in milliseconds.
            auto_enter: If True and text ends with \\n, press Enter key.
                        If False, type literal newline.

        Returns:
            True if successful.
        """
        if not self._wtype_path:
            self._wtype_path = shutil.which("wtype")
            if not self._wtype_path:
                return False

        # Handle newline based on auto_enter mode
        has_newline = text.endswith("\n")
        if has_newline and auto_enter:
            text = text[:-1]

        try:
            cmd = [self._wtype_path]
            if delay_ms > 0:
                cmd.extend(["-d", str(delay_ms)])
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
                    [self._wtype_path, "-k", "Return"],
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
        return "wtype"

    def send_newline(self) -> bool:
        """Send visual newline using Alt+Return."""
        if not self._wtype_path:
            self._wtype_path = shutil.which("wtype")
            if not self._wtype_path:
                return False

        try:
            # wtype -M alt -k Return -m alt
            result = subprocess.run(
                [self._wtype_path, "-M", "alt", "-k", "Return", "-m", "alt"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def send_submit(self) -> bool:
        """Send Return key to submit."""
        if not self._wtype_path:
            self._wtype_path = shutil.which("wtype")
            if not self._wtype_path:
                return False

        try:
            result = subprocess.run(
                [self._wtype_path, "-k", "Return"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False
