"""X11 window management using xdotool."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Optional

from claude_mic.window.base import Window, WindowManager

class XdotoolWindowManager(WindowManager):
    """Window management using xdotool (X11 only).

    Provides window search, text injection to specific windows,
    and focus management.
    """

    def __init__(self) -> None:
        """Initialize xdotool window manager."""
        super().__init__()
        self._xdotool: str | None = shutil.which("xdotool")
        self._wmctrl: str | None = shutil.which("wmctrl")

    def find_windows(self, query: str) -> list[Window]:
        """Find windows matching a query."""
        if not self._xdotool:
            return []

        windows = []
        query_lower = query.lower()

        # Search by name
        try:
            result = subprocess.run(
                [self._xdotool, "search", "--name", query],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for wid in result.stdout.strip().split("\n"):
                    if wid:
                        win = self._get_window_info(wid)
                        if win:
                            windows.append(win)
        except Exception:
            pass

        # Also search by class
        try:
            result = subprocess.run(
                [self._xdotool, "search", "--class", query],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for wid in result.stdout.strip().split("\n"):
                    if wid and not any(w.id == wid for w in windows):
                        win = self._get_window_info(wid)
                        if win:
                            windows.append(win)
        except Exception:
            pass

        # Filter by query (fuzzy match on name or class)
        filtered = []
        for win in windows:
            name_lower = win.name.lower()
            class_lower = win.class_name.lower()
            if query_lower in name_lower or query_lower in class_lower:
                filtered.append(win)

        return filtered or windows  # Return all if no filter match

    def list_windows(self) -> list[Window]:
        """List all windows."""
        if not self._wmctrl:
            return self._list_windows_xdotool()

        windows = []
        try:
            result = subprocess.run(
                [self._wmctrl, "-l", "-p"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split(None, 4)
                        if len(parts) >= 5:
                            wid = parts[0]
                            pid = int(parts[2]) if parts[2].isdigit() else None
                            name = parts[4] if len(parts) > 4 else ""
                            windows.append(Window(
                                id=wid,
                                name=name,
                                class_name=self._get_window_class(wid),
                                pid=pid,
                            ))
        except Exception:
            pass

        return windows

    def _list_windows_xdotool(self) -> list[Window]:
        """List windows using xdotool (fallback)."""
        if not self._xdotool:
            return []

        windows = []
        try:
            result = subprocess.run(
                [self._xdotool, "search", "--name", ""],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for wid in result.stdout.strip().split("\n"):
                    if wid:
                        win = self._get_window_info(wid)
                        if win:
                            windows.append(win)
        except Exception:
            pass

        return windows

    def _get_window_info(self, wid: str) -> Optional[Window]:
        """Get window info by ID."""
        if not self._xdotool:
            return None

        try:
            # Get window name
            name_result = subprocess.run(
                [self._xdotool, "getwindowname", wid],
                capture_output=True,
                text=True,
                timeout=2,
            )
            name = name_result.stdout.strip() if name_result.returncode == 0 else ""

            # Get window PID
            pid_result = subprocess.run(
                [self._xdotool, "getwindowpid", wid],
                capture_output=True,
                text=True,
                timeout=2,
            )
            pid = int(pid_result.stdout.strip()) if pid_result.returncode == 0 and pid_result.stdout.strip().isdigit() else None

            return Window(
                id=wid,
                name=name,
                class_name=self._get_window_class(wid),
                pid=pid,
            )
        except Exception:
            return None

    def _get_window_class(self, wid: str) -> str:
        """Get window class by ID."""
        if not self._xdotool:
            return ""

        try:
            # xprop is more reliable for class
            xprop = shutil.which("xprop")
            if xprop:
                result = subprocess.run(
                    [xprop, "-id", wid, "WM_CLASS"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    # Parse: WM_CLASS(STRING) = "instance", "class"
                    match = re.search(r'"([^"]+)",\s*"([^"]+)"', result.stdout)
                    if match:
                        return match.group(2)  # Return class name
        except Exception:
            pass

        return ""

    def get_active_window(self) -> Optional[Window]:
        """Get the currently focused window."""
        if not self._xdotool:
            return None

        try:
            result = subprocess.run(
                [self._xdotool, "getactivewindow"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                wid = result.stdout.strip()
                return self._get_window_info(wid)
        except Exception:
            pass

        return None

    def send_text(self, text: str, window: Optional[Window] = None) -> bool:
        """Send text to a window."""
        if not self._xdotool:
            return False

        target = window or self._target
        if not target:
            # Use active window
            return self._send_text_active(text)

        try:
            # Type to specific window without changing focus
            result = subprocess.run(
                [self._xdotool, "type", "--window", target.id, "--clearmodifiers", text],
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _send_text_active(self, text: str) -> bool:
        """Send text to active window."""
        if not self._xdotool:
            return False

        try:
            result = subprocess.run(
                [self._xdotool, "type", "--clearmodifiers", text],
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception:
            return False

    def focus_window(self, window: Window) -> bool:
        """Focus a window."""
        if not self._xdotool:
            return False

        try:
            result = subprocess.run(
                [self._xdotool, "windowactivate", "--sync", window.id],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def is_available(self) -> bool:
        """Check if xdotool is available."""
        return self._xdotool is not None

    def get_name(self) -> str:
        """Get window manager name."""
        return "xdotool"
