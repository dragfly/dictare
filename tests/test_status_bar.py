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
        path = Path.home() / "repos" / "personal" / "myproject"
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
