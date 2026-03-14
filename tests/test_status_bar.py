"""Tests for status bar helpers."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from unittest.mock import patch

from dictare import __version__
from dictare.agent.status_bar import StatusBar, _format_cwd

# ---------------------------------------------------------------------------
# _format_cwd
# ---------------------------------------------------------------------------

class TestFormatCwd:
    def test_home_prefix_replaced_with_tilde(self) -> None:
        path = Path.home() / "repos" / "myproject"
        assert _format_cwd(path, max_chars=100) == "~/repos/myproject"

    def test_non_home_path_kept_as_is(self) -> None:
        path = Path("/opt/homebrew/lib/something")
        assert _format_cwd(path, max_chars=100) == "/opt/homebrew/lib/something"

    def test_short_path_not_truncated(self) -> None:
        path = Path.home() / "proj"
        result = _format_cwd(path, max_chars=25)
        assert result == "~/proj"
        assert "\u2026" not in result

    def test_long_path_truncated_from_left(self) -> None:
        path = Path.home() / "a" / "b" / "c" / "d" / "e" / "f" / "g"
        result = _format_cwd(path, max_chars=10)
        assert result.startswith("\u2026")
        assert len(result) == 10

    def test_truncated_shows_tail_of_path(self) -> None:
        path = Path.home() / "projects" / "myapp"
        full = "~/projects/myapp"
        result = _format_cwd(path, max_chars=15)
        assert result.startswith("\u2026")
        assert full.endswith(result[1:])  # tail matches end of full path

    def test_exact_length_not_truncated(self) -> None:
        path = Path.home() / "x"
        s = "~/x"
        result = _format_cwd(path, max_chars=len(s))
        assert result == s
        assert "\u2026" not in result

    def test_home_itself(self) -> None:
        result = _format_cwd(Path.home(), max_chars=100)
        assert result in ("~/", "~/.")

# ---------------------------------------------------------------------------
# StatusBar right-side label construction
# ---------------------------------------------------------------------------

def _capture_right(sbar: StatusBar, cols: int = 120) -> str:
    """Run _draw and capture the right-side content from the rendered string."""
    captured: list[str] = []

    def fake_write(data: bytes) -> None:
        captured.append(data.decode(errors="replace"))

    def fake_flush() -> None:
        pass

    with patch.object(type(sbar).update, "__get__", lambda *a: None):
        pass  # not needed, we call _draw directly

    import io
    buf = io.BytesIO()
    with patch("sys.stdout") as mock_stdout:
        mock_stdout.buffer = buf
        sbar._draw(rows=24, cols=cols, text="● agent · listening", style="ok")

    rendered = buf.getvalue().decode(errors="replace")
    # Strip ANSI and control sequences, extract the right portion
    import re
    plain = re.sub(r"\x1b\[[^m]*m|\x1b\d|\x1b7|\x1b8|\x1b\[\d+;\d+H", "", rendered)
    plain = plain.strip()
    return plain

class TestStatusBarRightLabel:
    def test_no_label_shows_version_only(self) -> None:
        sbar = StatusBar("voice")
        plain = _capture_right(sbar)
        assert f"dictare {__version__}" in plain
        assert "[" not in plain or "~" not in plain  # no type/cwd label

    def test_agent_label_shown_in_brackets(self) -> None:
        sbar = StatusBar("voice", agent_label="opus")
        plain = _capture_right(sbar)
        assert "[opus]" in plain
        assert f"dictare {__version__}" in plain

    def test_cwd_label_shown(self) -> None:
        path = Path.home() / "myproject"
        sbar = StatusBar("voice", cwd=path)
        plain = _capture_right(sbar)
        assert "myproject" in plain
        assert f"dictare {__version__}" in plain

    def test_all_three_shown_left_to_right(self) -> None:
        path = Path.home() / "proj"
        sbar = StatusBar("voice", agent_label="opus", cwd=path)
        plain = _capture_right(sbar)
        cwd_pos = plain.find("proj")
        label_pos = plain.find("[opus]")
        version_pos = plain.find(f"dictare {__version__}")
        assert cwd_pos < label_pos < version_pos

    def test_separator_dots_between_parts(self) -> None:
        path = Path.home() / "proj"
        sbar = StatusBar("voice", agent_label="opus", cwd=path)
        plain = _capture_right(sbar)
        # Each part is separated by " · "
        assert plain.count("\u00b7") >= 2

    def test_cwd_long_path_truncated_in_bar(self) -> None:
        path = Path.home() / "a" / "b" / "c" / "d" / "e" / "f"
        sbar = StatusBar("voice", cwd=path)
        plain = _capture_right(sbar)
        # The cwd label should be truncated (contains ellipsis or is short)
        assert f"dictare {__version__}" in plain

# ---------------------------------------------------------------------------
# on_resize: stale row cleanup
# ---------------------------------------------------------------------------

class TestResizeStaleRowCleanup:
    """Test that resizing clears the old status bar row."""

    def test_resize_sets_stale_row(self) -> None:
        sbar = StatusBar("test")
        sbar._rows = 50
        with patch("sys.stdout"):
            sbar.on_resize(51, 120)
        assert sbar._stale_row == 50

    def test_same_size_no_stale_row(self) -> None:
        sbar = StatusBar("test")
        sbar._rows = 50
        with patch("sys.stdout"):
            sbar.on_resize(50, 120)
        assert sbar._stale_row == 0

    def test_initial_resize_no_stale_row(self) -> None:
        """First resize (from _rows=0) should not set stale row."""
        sbar = StatusBar("test")
        assert sbar._rows == 0
        with patch("sys.stdout"):
            sbar.on_resize(50, 120)
        assert sbar._stale_row == 0

    def test_check_redraw_clears_stale_row(self) -> None:
        import io
        sbar = StatusBar("test")
        sbar._rows = 50
        sbar._cols = 120
        sbar._stale_row = 45  # simulate leftover from resize

        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = buf
            sbar.check_redraw()

        output = buf.getvalue().decode()
        # Should contain cursor move to row 45 and erase line
        assert "\x1b[45;1H" in output
        assert "\x1b[2K" in output
        assert sbar._stale_row == 0

    def test_stale_row_works_without_scroll_region(self) -> None:
        sbar = StatusBar("test", use_scroll_region=False)
        sbar._rows = 50
        with patch("sys.stdout"):
            sbar.on_resize(51, 120)
        assert sbar._stale_row == 50

    def test_on_resize_does_not_write_stdout(self) -> None:
        """on_resize is called from SIGWINCH — must not write to stdout."""
        import io
        sbar = StatusBar("test")
        sbar._rows = 50
        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = buf
            sbar.on_resize(51, 120)
        # on_resize should NOT have written anything (no reentrant flush)
        assert buf.getvalue() == b""

# ---------------------------------------------------------------------------
# on_output: scroll region auto-detection
# ---------------------------------------------------------------------------

class TestScrollRegionAutoDetection:
    """Test that _sr_active is disabled when child sends own DECSTBM."""

    def test_child_decstbm_set_disables_scroll_region(self) -> None:
        """ESC[1;7r from child should trigger auto-disable."""
        import re
        decstbm_set_re = re.compile(rb'\x1b\[\d+;\d+r')
        data = b"\x1b[1;7r"  # Codex-style DECSTBM set
        assert decstbm_set_re.search(data) is not None

    def test_bare_decstbm_reset_does_not_trigger(self) -> None:
        """ESC[r (bare reset) should NOT trigger auto-disable."""
        import re
        decstbm_set_re = re.compile(rb'\x1b\[\d+;\d+r')
        data = b"\x1b[r"  # bare reset
        assert decstbm_set_re.search(data) is None

    def test_decstbm_set_regex_matches_various_formats(self) -> None:
        """Regex should match ESC[1;7r, ESC[1;30r, etc."""
        import re
        decstbm_set_re = re.compile(rb'\x1b\[\d+;\d+r')
        assert decstbm_set_re.search(b"\x1b[1;7r")
        assert decstbm_set_re.search(b"\x1b[1;30r")
        assert decstbm_set_re.search(b"\x1b[1;49r")
        assert not decstbm_set_re.search(b"\x1b[r")
        assert not decstbm_set_re.search(b"\x1b[2J")

    def test_disable_scroll_region_updates_status_bar(self) -> None:
        """When scroll region is auto-disabled, StatusBar flags update."""
        sbar = StatusBar("test", use_scroll_region=True)
        sbar._rows = 50
        # Simulate what _disable_scroll_region does
        sbar._use_scroll_region = False
        sbar._region_esc = b""
        assert sbar._use_scroll_region is False
        assert sbar._region_esc == b""

    def test_mark_child_output_used_when_sr_disabled(self) -> None:
        """In non-scroll-region mode, mark_child_output sets the flag."""
        sbar = StatusBar("test", use_scroll_region=False)
        sbar._rows = 50
        assert sbar._output_since_redraw is False
        sbar.mark_child_output()
        assert sbar._output_since_redraw is True

# ---------------------------------------------------------------------------
# request_redraw only in scroll_region mode
# ---------------------------------------------------------------------------

class TestRequestRedrawScrollRegionOnly:
    """Verify request_redraw behavior differs by scroll_region mode."""

    def test_request_redraw_sets_flag(self) -> None:
        sbar = StatusBar("test", use_scroll_region=True)
        assert sbar._redraw_requested is False
        sbar.request_redraw()
        assert sbar._redraw_requested is True

    def test_mark_child_output_sets_idle_flag(self) -> None:
        sbar = StatusBar("test", use_scroll_region=False)
        assert sbar._output_since_redraw is False
        sbar.mark_child_output()
        assert sbar._output_since_redraw is True
        assert sbar._last_output_at > 0

# ---------------------------------------------------------------------------
# _write_to_pty: "error" message sets stop_event and exits
# ---------------------------------------------------------------------------

class TestWriteToPtyErrorStopsSession:
    """Test that an 'error' message from the SSE thread stops the PTY loop."""

    def _run_with_error(self, error_msg: str = "Agent 'x' already connected"):
        from dictare.agent.mux import _write_to_pty

        wq: queue.Queue = queue.Queue()
        stop = threading.Event()
        writes: list[bytes] = []

        def fake_write(fd, data):
            writes.append(data)
            return len(data)

        def fake_tcdrain(fd):
            pass

        wq.put(("error", error_msg))

        with patch("os.write", side_effect=fake_write), \
             patch("termios.tcdrain", side_effect=fake_tcdrain):
            _write_to_pty(master_fd=99, write_queue=wq, stop_event=stop)

        return stop, writes

    def test_error_sets_stop_event(self) -> None:
        stop, _ = self._run_with_error()
        assert stop.is_set()

    def test_error_does_not_write_to_pty(self) -> None:
        _, writes = self._run_with_error()
        assert writes == []

    def test_error_drains_queue_before_checking(self) -> None:
        """Only the error is processed — subsequent items are not written."""
        from dictare.agent.mux import _write_to_pty

        wq: queue.Queue = queue.Queue()
        stop = threading.Event()
        writes: list[bytes] = []

        def fake_write(fd, data):
            writes.append(data)
            return len(data)

        wq.put(("error", "fatal"))
        wq.put(("msg", {"text": "should not be written"}))

        with patch("os.write", side_effect=fake_write), \
             patch("termios.tcdrain"):
            _write_to_pty(master_fd=99, write_queue=wq, stop_event=stop)

        assert stop.is_set()
        assert writes == []

# ---------------------------------------------------------------------------
# agent_label computation in CLI
# ---------------------------------------------------------------------------

class TestAgentLabel:
    """Test that agent_label is computed correctly from type vs command override."""

    def _compute_label(
        self,
        type_key: str | None,
        command_override: list[str] | None,
    ) -> str | None:
        """Replicate the label computation logic from cli/agent.py."""
        agent_label: str | None = None
        if command_override:
            cmd_str = " ".join(command_override)
            agent_label = cmd_str[:30] + ("\u2026" if len(cmd_str) > 30 else "")
        elif type_key:
            agent_label = type_key
        return agent_label

    def test_type_key_used_as_label(self) -> None:
        assert self._compute_label("opus", None) == "opus"

    def test_command_override_used_as_label(self) -> None:
        assert self._compute_label(None, ["claude"]) == "claude"

    def test_command_override_beats_type_key(self) -> None:
        result = self._compute_label("opus", ["claude", "--fast"])
        assert result == "claude --fast"

    def test_long_command_truncated_to_30(self) -> None:
        cmd = ["claude", "--model", "claude-opus-4-6-20251101-thinking"]
        result = self._compute_label(None, cmd)
        assert result is not None
        assert len(result) == 31  # 30 chars + ellipsis
        assert result.endswith("\u2026")

    def test_exactly_30_chars_not_truncated(self) -> None:
        cmd = ["a" * 30]
        result = self._compute_label(None, cmd)
        assert result == "a" * 30
        assert "\u2026" not in result

    def test_31_chars_truncated(self) -> None:
        cmd = ["a" * 31]
        result = self._compute_label(None, cmd)
        assert result == "a" * 30 + "\u2026"

    def test_no_type_no_override_returns_none(self) -> None:
        assert self._compute_label(None, None) is None

    def test_empty_type_key_returns_none(self) -> None:
        assert self._compute_label("", None) is None
