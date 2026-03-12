"""Persistent status bar using DECSTBM scroll region.

Reserves the last terminal row for a status indicator. The child process
sees one fewer row via TIOCSWINSZ, so its output never overwrites the bar.

Compatible with: iTerm2, Terminal.app, gnome-terminal, Konsole, kitty,
alacritty, wezterm, ghostty.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path

from dictare import __version__

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _format_cwd(path: Path, max_chars: int = 25) -> str:
    """Format a directory path for the status bar.

    Replaces the home directory prefix with ``~``.  If the result is still
    longer than *max_chars*, truncates from the left with an ellipsis so
    the trailing portion of the path (the most relevant part) is visible.
    """
    try:
        rel = path.relative_to(Path.home())
        s = "~/" + str(rel)
    except ValueError:
        s = str(path)
    if len(s) <= max_chars:
        return s
    return "\u2026" + s[-(max_chars - 1):]

_STATUS_STYLES = {
    "ok": "\x1b[48;5;236m\x1b[38;5;114m",        # soft green on dark gray
    "warn": "\x1b[48;5;236m\x1b[38;5;229m",       # warm yellow on dark gray
    "error": "\x1b[48;5;236m\x1b[38;5;210m",      # soft red on dark gray
    "dim": "\x1b[48;5;236m\x1b[38;5;245m",        # gray on dark gray (off)
}


class StatusBar:
    """Terminal status bar occupying the last row.

    Thread-safe: ``update()`` can be called from any thread.
    ``check_redraw()`` must be called from the main loop thread that
    owns stdout writes.
    """

    def __init__(
        self,
        agent_id: str,
        agent_label: str | None = None,
        cwd: Path | None = None,
        use_scroll_region: bool = True,
    ) -> None:
        self._text = f"\u25cb {agent_id} \u00b7 connecting..."
        self._style = "warn"
        self._agent_label = agent_label
        self._cwd_label = _format_cwd(cwd) if cwd is not None else None
        self._use_scroll_region = use_scroll_region
        self._lock = threading.Lock()
        self._rows = 0             # cached terminal size
        self._cols = 0
        # Reactive redraw: set by request_redraw() when child clears screen
        self._redraw_requested = False
        # After resize, schedule a single deferred redraw
        self._resize_redraw_at = 0.0  # timestamp for deferred resize redraw
        # Idle-based redraw for no-scroll-region mode: redraw status bar
        # only after child output has been quiet for a short period, to
        # avoid interleaving save/restore cursor with the child's own
        # cursor movement (which corrupts relative cursor-up agents).
        self._output_since_redraw = False
        self._last_output_at = 0.0
        # Pre-built scroll region escape (updated on resize)
        self._region_esc = b""

    # -- public API -----------------------------------------------------------

    def init(self, rows: int, cols: int) -> None:
        """Set up scroll region (if enabled) and draw initial status bar."""
        self._rows = rows
        self._cols = cols
        if self._use_scroll_region:
            self._region_esc = f"\x1b7\x1b[1;{rows - 1}r\x1b8".encode()
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
        """Handle terminal resize — re-init scroll region, schedule one redraw."""
        self._rows = rows
        self._cols = cols
        if self._use_scroll_region:
            self._region_esc = f"\x1b7\x1b[1;{rows - 1}r\x1b8".encode()
            self._init_scroll_region(rows, cols)
        # Single deferred redraw 200ms after last resize event (debounce).
        self._resize_redraw_at = time.monotonic() + 0.2

    def request_redraw(self) -> None:
        """Request a status bar redraw on next check_redraw() cycle.

        Called from on_output() when the child emits a screen-clear
        sequence (e.g. \\x1b[2J). This replaces the old periodic timer
        with a deterministic, reactive trigger.
        """
        self._redraw_requested = True

    def after_child_output(self) -> None:
        """Re-establish scroll region after relaying child output.

        Always active: the child may reset scroll region at any time
        (e.g. Ctrl+O mode toggle in Claude Code). Writing the pre-built
        escape (~15 bytes, no flush) after every output chunk is cheap
        and keeps our region intact.
        """
        if self._region_esc:
            sys.stdout.buffer.write(self._region_esc)

    def mark_child_output(self) -> None:
        """Record that child produced output (no scroll region mode).

        Instead of redrawing immediately (which injects save/restore cursor
        sequences that corrupt relative-cursor agents like Gemini),
        this sets a flag so that ``check_redraw()`` can repaint the status
        bar after a brief idle period (~150 ms of no output).
        """
        self._output_since_redraw = True
        self._last_output_at = time.monotonic()

    def check_redraw(self) -> None:
        """Called from main loop — repaint status bar when needed.

        Reactive approach: redraw only when explicitly requested
        (child screen clear) or after a resize debounce.
        No periodic timer — zero interference with child rendering.
        """
        now = time.monotonic()

        # Deferred resize redraw (single, after debounce)
        if self._resize_redraw_at and now >= self._resize_redraw_at:
            self._resize_redraw_at = 0.0
            rows, cols = self._get_winsize()
            if self._use_scroll_region:
                self._init_scroll_region(rows, cols)
            with self._lock:
                self._draw(rows, cols, self._text, self._style)
            return

        # Reactive redraw: child cleared the screen
        if self._redraw_requested:
            self._redraw_requested = False
            if self._use_scroll_region:
                rows, cols = self._get_winsize()
                self._init_scroll_region(rows, cols)
                with self._lock:
                    self._draw(rows, cols, self._text, self._style)
            else:
                with self._lock:
                    self._draw(self._rows, self._cols, self._text, self._style)
            return

        # Idle-based redraw for no-scroll-region mode: repaint once after
        # child output has been quiet for 150ms.  This avoids injecting
        # save/restore cursor during active output (which corrupts agents
        # that use relative cursor movement like Gemini CLI).
        if (
            not self._use_scroll_region
            and self._output_since_redraw
            and now - self._last_output_at >= 0.15
        ):
            self._output_since_redraw = False
            with self._lock:
                self._draw(self._rows, self._cols, self._text, self._style)

    def cleanup(self) -> None:
        """Reset scroll region and clear status bar line."""
        rows, cols = self._get_winsize()
        if self._use_scroll_region:
            sys.stdout.buffer.write(
                f"\x1b[r\x1b[{rows};1H\x1b[2K\n".encode()
            )
        else:
            sys.stdout.buffer.write(
                f"\x1b[{rows};1H\x1b[2K\n".encode()
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

    def _draw(self, rows: int, cols: int, text: str, style: str) -> None:
        """Render the status bar on the last row."""
        parts: list[str] = []
        if self._cwd_label:
            parts.append(self._cwd_label)
        if self._agent_label:
            parts.append(f"[{self._agent_label}]")
        parts.append(f"dictare {__version__}")
        right = " \u00b7 ".join(parts)
        visible_text_len = len(_ANSI_RE.sub("", text))
        gap = cols - visible_text_len - len(right)
        if gap >= 2:
            display = text + " " * gap + right
        else:
            display = text[:cols]
        ansi = _STATUS_STYLES.get(style, _STATUS_STYLES["ok"])
        sys.stdout.buffer.write(
            f"\x1b7\x1b[{rows};1H{ansi}{display:<{cols}}\x1b[0m\x1b8".encode()
        )
        sys.stdout.buffer.flush()
