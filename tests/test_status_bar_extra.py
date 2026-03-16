"""Additional tests for status bar (dictare.agent.status_bar)."""

from __future__ import annotations

import io
import time
from pathlib import Path
from unittest.mock import patch

from dictare.agent.status_bar import _STATUS_STYLES, StatusBar, _format_cwd

# ---------------------------------------------------------------------------
# StatusBar._draw rendering
# ---------------------------------------------------------------------------

class TestStatusBarDraw:
    def _render(self, sbar: StatusBar, text: str = "test", style: str = "ok",
                rows: int = 24, cols: int = 80) -> str:
        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = buf
            sbar._draw(rows, cols, text, style)
        return buf.getvalue().decode(errors="replace")

    def test_draw_outputs_ansi(self) -> None:
        sbar = StatusBar("test")
        output = self._render(sbar)
        assert "\x1b[" in output

    def test_draw_positions_at_last_row(self) -> None:
        sbar = StatusBar("test")
        output = self._render(sbar, rows=30, cols=80)
        assert "\x1b[30;1H" in output

    def test_draw_resets_cursor(self) -> None:
        sbar = StatusBar("test")
        output = self._render(sbar)
        # Save (\x1b7) and restore (\x1b8)
        assert "\x1b7" in output
        assert "\x1b8" in output

    def test_draw_uses_style(self) -> None:
        sbar = StatusBar("test")
        for style_name, style_code in _STATUS_STYLES.items():
            output = self._render(sbar, style=style_name)
            assert style_code in output

    def test_draw_unknown_style_falls_back_to_ok(self) -> None:
        sbar = StatusBar("test")
        output = self._render(sbar, style="nonexistent")
        assert _STATUS_STYLES["ok"] in output

    def test_draw_truncates_long_text(self) -> None:
        sbar = StatusBar("test")
        long_text = "x" * 200
        output = self._render(sbar, text=long_text, cols=40)
        # Should still have proper escapes, not overflow
        assert "\x1b[" in output

    def test_draw_with_ansi_text(self) -> None:
        sbar = StatusBar("test")
        ansi_text = "\x1b[38;5;210mrecording\x1b[0m"
        output = self._render(sbar, text=ansi_text, cols=120)
        # ANSI length calculation should handle escape codes
        assert "\x1b[" in output


# ---------------------------------------------------------------------------
# StatusBar.text property
# ---------------------------------------------------------------------------

class TestStatusBarTextProperty:
    def test_text_returns_initial(self) -> None:
        sbar = StatusBar("agent1")
        assert "agent1" in sbar.text

    def test_text_updated_after_update(self) -> None:
        sbar = StatusBar("agent1")
        with patch.object(sbar, "_draw"), \
             patch.object(sbar, "_get_winsize", return_value=(24, 80)):
            sbar.update("new text", "ok")
        assert sbar.text == "new text"


# ---------------------------------------------------------------------------
# StatusBar.init
# ---------------------------------------------------------------------------

class TestStatusBarInit:
    def test_init_scroll_region(self) -> None:
        sbar = StatusBar("test", use_scroll_region=True)
        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = buf
            sbar.init(30, 120)
        output = buf.getvalue().decode()
        # Should set DECSTBM: ESC[1;29r
        assert "\x1b[1;29r" in output
        assert sbar._rows == 30
        assert sbar._cols == 120

    def test_init_no_scroll_region(self) -> None:
        sbar = StatusBar("test", use_scroll_region=False)
        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = buf
            sbar.init(30, 120)
        output = buf.getvalue().decode()
        # Should NOT set scroll region
        assert "\x1b[1;29r" not in output


# ---------------------------------------------------------------------------
# StatusBar.cleanup
# ---------------------------------------------------------------------------

class TestStatusBarCleanup:
    def test_cleanup_resets_scroll_region(self) -> None:
        sbar = StatusBar("test", use_scroll_region=True)
        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout, \
             patch.object(sbar, "_get_winsize", return_value=(24, 80)):
            mock_stdout.buffer = buf
            sbar.cleanup()
        output = buf.getvalue().decode()
        assert "\x1b[r" in output

    def test_cleanup_without_scroll_region(self) -> None:
        sbar = StatusBar("test", use_scroll_region=False)
        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout, \
             patch.object(sbar, "_get_winsize", return_value=(24, 80)):
            mock_stdout.buffer = buf
            sbar.cleanup()
        output = buf.getvalue().decode()
        # Clears the last line
        assert "\x1b[24;1H" in output
        assert "\x1b[2K" in output


# ---------------------------------------------------------------------------
# StatusBar.after_child_output
# ---------------------------------------------------------------------------

class TestAfterChildOutput:
    def test_writes_region_escape_when_set(self) -> None:
        sbar = StatusBar("test", use_scroll_region=True)
        sbar._region_esc = b"\x1b7\x1b[1;29r\x1b8"
        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = buf
            sbar.after_child_output()
        assert buf.getvalue() == b"\x1b7\x1b[1;29r\x1b8"

    def test_noop_when_no_region_escape(self) -> None:
        sbar = StatusBar("test", use_scroll_region=False)
        sbar._region_esc = b""
        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = buf
            sbar.after_child_output()
        assert buf.getvalue() == b""


# ---------------------------------------------------------------------------
# StatusBar.check_redraw — idle-based (no scroll region)
# ---------------------------------------------------------------------------

class TestCheckRedrawIdle:
    def test_idle_redraw_after_150ms(self) -> None:
        sbar = StatusBar("test", use_scroll_region=False)
        sbar._rows = 24
        sbar._cols = 80
        sbar._output_since_redraw = True
        # Simulate 200ms ago
        sbar._last_output_at = time.monotonic() - 0.2

        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = buf
            sbar.check_redraw()

        assert sbar._output_since_redraw is False
        assert buf.getvalue() != b""  # something was drawn

    def test_no_redraw_if_output_recent(self) -> None:
        sbar = StatusBar("test", use_scroll_region=False)
        sbar._rows = 24
        sbar._cols = 80
        sbar._output_since_redraw = True
        sbar._last_output_at = time.monotonic()  # just now

        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = buf
            sbar.check_redraw()

        assert sbar._output_since_redraw is True  # still pending
        assert buf.getvalue() == b""


# ---------------------------------------------------------------------------
# _format_cwd edge cases
# ---------------------------------------------------------------------------

class TestFormatCwdEdgeCases:
    def test_root_path(self) -> None:
        result = _format_cwd(Path("/"), max_chars=100)
        assert result == "/"

    def test_max_chars_1(self) -> None:
        result = _format_cwd(Path("/a/b/c/d"), max_chars=2)
        assert len(result) == 2
        assert result.startswith("\u2026")
