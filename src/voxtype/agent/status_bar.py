"""Persistent status bar using DECSTBM scroll region.

Reserves the last terminal row for a status indicator. The child process
sees one fewer row via TIOCSWINSZ, so its output never overwrites the bar.

Compatible with: iTerm2, Terminal.app, gnome-terminal, Konsole, kitty,
alacritty, wezterm, ghostty.
"""

from __future__ import annotations

import sys
import threading
import time

from voxtype import __version__

_STATUS_STYLES = {
    "ok": "\x1b[48;5;236m\x1b[38;5;114m",        # soft green on dark gray
    "warn": "\x1b[48;5;236m\x1b[38;5;229m",       # warm yellow on dark gray
    "error": "\x1b[48;5;236m\x1b[38;5;210m",      # soft red on dark gray
}

class StatusBar:
    """Terminal status bar occupying the last row.

    Thread-safe: ``update()`` can be called from any thread.
    ``check_redraw()`` must be called from the main loop thread that
    owns stdout writes.
    """

    def __init__(self, agent_id: str) -> None:
        self._text = f"\u25cb {agent_id} \u00b7 connecting..."
        self._style = "warn"
        self._lock = threading.Lock()
        self._redraw_after = 0.0  # monotonic timestamp, 0 = none pending

    # -- public API -----------------------------------------------------------

    def init(self, rows: int, cols: int) -> None:
        """Set up scroll region and draw initial status bar."""
        self._init_scroll_region(rows, cols)
        with self._lock:
            self._draw(rows, cols, self._text, self._style)

    def update(self, text: str, style: str = "ok") -> None:
        """Update status text (callable from any thread)."""
        with self._lock:
            self._text = text
            self._style = style
        rows, cols = self._get_winsize()
        self._draw(rows, cols, text, style)

    def on_resize(self, rows: int, cols: int) -> None:
        """Handle terminal resize — re-init scroll region, schedule redraw."""
        self._init_scroll_region(rows, cols)
        self._redraw_after = time.monotonic() + 0.15

    def check_redraw(self) -> None:
        """Called from main loop — redraw if deferred timer has expired."""
        deadline = self._redraw_after
        if deadline and time.monotonic() >= deadline:
            self._redraw_after = 0.0
            rows, cols = self._get_winsize()
            self._init_scroll_region(rows, cols)
            with self._lock:
                self._draw(rows, cols, self._text, self._style)

    def cleanup(self) -> None:
        """Reset scroll region and clear status bar line."""
        rows, cols = self._get_winsize()
        sys.stdout.buffer.write(
            f"\x1b[r\x1b[{rows};1H\x1b[2K\n".encode()
        )
        sys.stdout.buffer.flush()

    @property
    def text(self) -> str:
        with self._lock:
            return self._text

    # -- private --------------------------------------------------------------

    @staticmethod
    def _get_winsize() -> tuple[int, int]:
        """Get current terminal size (import-free to avoid circular deps)."""
        import struct
        import termios
        from fcntl import ioctl

        try:
            winsize = struct.pack("HHHH", 0, 0, 0, 0)
            result = ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, winsize)
            rows, cols, _, _ = struct.unpack("HHHH", result)
            return rows, cols
        except OSError:
            return 24, 80

    @staticmethod
    def _init_scroll_region(rows: int, cols: int) -> None:
        """Set scroll region to rows 1..N-1."""
        # DECSTBM resets cursor to (1,1) — save/restore around it
        sys.stdout.buffer.write(f"\x1b7\x1b[1;{rows - 1}r\x1b8".encode())
        sys.stdout.buffer.flush()

    @staticmethod
    def _draw(rows: int, cols: int, text: str, style: str) -> None:
        """Render the status bar on the last row."""
        right = f"voxtype {__version__}"
        gap = cols - len(text) - len(right)
        if gap >= 2:
            display = text + " " * gap + right
        else:
            display = text[:cols]
        ansi = _STATUS_STYLES.get(style, _STATUS_STYLES["ok"])
        sys.stdout.buffer.write(
            f"\x1b7\x1b[{rows};1H{ansi}{display:<{cols}}\x1b[0m\x1b8".encode()
        )
        sys.stdout.buffer.flush()
