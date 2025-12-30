"""Clipboard-based text injection (fallback)."""

from __future__ import annotations

import shutil
import subprocess

from voxtype.injection.base import TextInjector


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

        # Linux - detect session type
        session_type = os.environ.get("XDG_SESSION_TYPE", "")
        is_wayland = os.environ.get("WAYLAND_DISPLAY") or session_type == "wayland"

        if is_wayland:
            if shutil.which("wl-copy"):
                return ["wl-copy"]
        else:
            # X11 or unknown
            if shutil.which("xclip"):
                return ["xclip", "-selection", "clipboard"]
            if shutil.which("xsel"):
                return ["xsel", "--clipboard", "--input"]

        return None

    def is_available(self) -> bool:
        """Check if clipboard is available."""
        self._copy_cmd = self._detect_copy_command()
        return self._copy_cmd is not None

    def type_text(self, text: str, delay_ms: int = 0, auto_paste: bool = False) -> bool:
        """Copy text to clipboard and optionally paste.

        Args:
            text: Text to copy to clipboard.
            delay_ms: Ignored for clipboard operations.
            auto_paste: If True, automatically send Ctrl+Shift+V after copying.

        Returns:
            True if successful.
        """
        if not self._copy_cmd:
            self._copy_cmd = self._detect_copy_command()
            if not self._copy_cmd:
                return False

        # Handle Enter separately - pasting \n doesn't trigger Enter
        send_enter = text.endswith("\n")
        if send_enter:
            text = text[:-1]

        try:
            proc = subprocess.Popen(
                self._copy_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.communicate(input=text.encode("utf-8"), timeout=10)
            if proc.returncode != 0:
                return False

            # Auto-paste with Ctrl+Shift+V
            if auto_paste:
                self._send_paste_shortcut()
                # Send Enter separately if needed
                if send_enter:
                    self._send_enter_key()

            return True
        except subprocess.TimeoutExpired:
            proc.kill()
            return False
        except Exception:
            return False

    def _send_paste_shortcut(self) -> None:
        """Send Ctrl+V (or Cmd+V on macOS) to paste."""
        import sys
        import time

        # Small delay to ensure clipboard is ready
        time.sleep(0.05)

        try:
            if sys.platform == "darwin":
                # macOS: Cmd+V
                subprocess.run(
                    ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
                    capture_output=True,
                    timeout=5,
                )
            else:
                # Linux: try ydotool first, then xdotool
                # Use Ctrl+Shift+V (terminal paste) instead of Ctrl+V (image paste in some apps)
                ydotool = shutil.which("ydotool")
                if ydotool:
                    subprocess.run(
                        # Ctrl+Shift+V: Ctrl(29) down, Shift(42) down, V(47) down/up, Shift up, Ctrl up
                        [ydotool, "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"],
                        capture_output=True,
                        timeout=5,
                    )
                else:
                    xdotool = shutil.which("xdotool")
                    if xdotool:
                        subprocess.run(
                            [xdotool, "key", "ctrl+shift+v"],
                            capture_output=True,
                            timeout=5,
                        )
        except Exception:
            pass  # Best effort, don't fail if paste doesn't work

    def _send_enter_key(self) -> None:
        """Send Enter key."""
        import sys
        import time

        # Wait for paste to complete before sending Enter
        time.sleep(0.2)

        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["osascript", "-e", 'tell application "System Events" to keystroke return'],
                    capture_output=True,
                    timeout=5,
                )
            else:
                ydotool = shutil.which("ydotool")
                if ydotool:
                    subprocess.run(
                        [ydotool, "key", "28:1", "28:0"],  # KEY_ENTER
                        capture_output=True,
                        timeout=5,
                    )
                else:
                    xdotool = shutil.which("xdotool")
                    if xdotool:
                        subprocess.run(
                            [xdotool, "key", "Return"],
                            capture_output=True,
                            timeout=5,
                        )
        except Exception:
            pass

    def get_name(self) -> str:
        """Get injector name."""
        return "clipboard"
