"""Clipboard-based text injection (fallback)."""

from __future__ import annotations

import shutil
import subprocess

from claude_mic.injection.base import TextInjector


class ClipboardInjector(TextInjector):
    """Clipboard-based text injection.

    Copies text to clipboard. User must paste manually.
    Works on Linux (X11/Wayland) and macOS.
    """

    def __init__(self) -> None:
        """Initialize clipboard injector."""
        self._copy_cmd: list[str] | None = None

    def _detect_copy_command(self) -> list[str] | None:
        """Detect the appropriate clipboard copy command."""
        import os
        import sys

        if sys.platform == "darwin":
            if shutil.which("pbcopy"):
                return ["pbcopy"]
            return None

        # Linux
        if os.environ.get("WAYLAND_DISPLAY"):
            if shutil.which("wl-copy"):
                return ["wl-copy"]
        else:
            if shutil.which("xclip"):
                return ["xclip", "-selection", "clipboard"]
            if shutil.which("xsel"):
                return ["xsel", "--clipboard", "--input"]

        # Fallback: try wl-copy anyway (might work in some setups)
        if shutil.which("wl-copy"):
            return ["wl-copy"]

        return None

    def is_available(self) -> bool:
        """Check if clipboard is available."""
        self._copy_cmd = self._detect_copy_command()
        return self._copy_cmd is not None

    def type_text(self, text: str, delay_ms: int = 0) -> bool:
        """Copy text to clipboard.

        Note: delay_ms is ignored for clipboard operations.

        Args:
            text: Text to copy to clipboard.
            delay_ms: Ignored.

        Returns:
            True if successful.
        """
        if not self._copy_cmd:
            self._copy_cmd = self._detect_copy_command()
            if not self._copy_cmd:
                return False

        try:
            proc = subprocess.Popen(
                self._copy_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.communicate(input=text.encode("utf-8"), timeout=10)
            return proc.returncode == 0
        except subprocess.TimeoutExpired:
            proc.kill()
            return False
        except Exception:
            return False

    def get_name(self) -> str:
        """Get injector name."""
        return "clipboard"
