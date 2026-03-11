"""Tests for the transcribe CLI command."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

from dictare.cli.transcribe import process_messages

def _make_msg(text: str, *, msg_type: str = "transcription", submit: bool = False):
    """Create a mock transcription message."""
    msg = MagicMock()
    msg.type = msg_type
    msg.text = text
    if submit:
        msg.x_input = MagicMock(ops=["submit"])
    else:
        msg.x_input = None
    msg.additional_properties = {}
    return msg

def _run_process(messages: list, *, auto_submit: bool = False) -> str:
    """Run process_messages and return captured output."""
    output = io.StringIO()
    process_messages(iter(messages), auto_submit=auto_submit, output=output)
    return output.getvalue()

class TestAutoSubmit:
    """Tests for --auto-submit mode (print each transcription immediately)."""

    def test_prints_each_transcription(self):
        result = _run_process([
            _make_msg("hello"),
            _make_msg("world"),
        ], auto_submit=True)
        assert "hello\n" in result
        assert "world\n" in result

    def test_skips_empty_text(self):
        result = _run_process([
            _make_msg(""),
            _make_msg("  "),
            _make_msg("actual text"),
        ], auto_submit=True)
        lines = [line for line in result.strip().split("\n") if line.strip()]
        assert len(lines) == 1
        assert lines[0] == "actual text"

    def test_skips_non_transcription_messages(self):
        result = _run_process([
            _make_msg("speech text", msg_type="speech"),
            _make_msg("hello"),
        ], auto_submit=True)
        assert "speech text" not in result
        assert "hello" in result

class TestAccumulate:
    """Tests for default mode (accumulate until submit)."""

    def test_accumulates_until_submit(self):
        result = _run_process([
            _make_msg("hello"),
            _make_msg("world"),
            _make_msg("", submit=True),
        ])
        assert "hello world\n" in result

    def test_exits_after_submit(self):
        """In accumulate mode, exits after first submit (one-shot)."""
        result = _run_process([
            _make_msg("first"),
            _make_msg("", submit=True),
            _make_msg("second"),  # should be ignored
        ])
        lines = [line for line in result.strip().split("\n") if line.strip()]
        assert len(lines) == 1
        assert lines[0] == "first"

    def test_submit_with_text(self):
        result = _run_process([
            _make_msg("hello"),
            _make_msg("world", submit=True),
        ])
        assert "hello world\n" in result

    def test_empty_submit_ignored(self):
        result = _run_process([
            _make_msg("", submit=True),
        ])
        assert result.strip() == ""

    def test_remaining_buffer_flushed(self):
        """Unflushed buffer is printed when stream ends."""
        result = _run_process([
            _make_msg("orphan text"),
        ])
        assert "orphan text\n" in result

    def test_ignores_messages_after_submit(self):
        """After submit, remaining messages are ignored (one-shot)."""
        result = _run_process([
            _make_msg("first"),
            _make_msg("", submit=True),
            _make_msg("second"),
            _make_msg("third"),
        ])
        lines = [line for line in result.strip().split("\n") if line.strip()]
        assert len(lines) == 1
        assert lines[0] == "first"

class TestEdgeCases:
    """Edge cases."""

    def test_empty_stream(self):
        result = _run_process([])
        assert result == ""

    def test_only_non_transcription(self):
        result = _run_process([
            _make_msg("a", msg_type="speech"),
            _make_msg("b", msg_type="status"),
        ])
        assert result == ""

    def test_none_text_treated_as_empty(self):
        msg = MagicMock()
        msg.type = "transcription"
        msg.text = None
        msg.x_input = None
        msg.additional_properties = {}
        result = _run_process([msg], auto_submit=True)
        assert result.strip() == ""
