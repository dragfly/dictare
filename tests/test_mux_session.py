"""Tests for mux session helpers: KeystrokeCounter, session logging, _write_all."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from dictare import __version__
from dictare.agent.mux import (
    KeystrokeCounter,
    _get_session_log_path,
    _log_event,
    _write_session_end,
    _write_session_start,
)
from dictare.agent.pty_session import _write_all

# ---------------------------------------------------------------------------
# KeystrokeCounter
# ---------------------------------------------------------------------------


class TestKeystrokeCounter:
    def test_initial_count_zero(self) -> None:
        kc = KeystrokeCounter()
        assert kc.count == 0

    def test_add_increments(self) -> None:
        kc = KeystrokeCounter()
        kc.add(5)
        assert kc.count == 5

    def test_add_multiple_times(self) -> None:
        kc = KeystrokeCounter()
        kc.add(3)
        kc.add(7)
        kc.add(1)
        assert kc.count == 11

    def test_add_zero_unchanged(self) -> None:
        kc = KeystrokeCounter()
        kc.add(10)
        kc.add(0)
        assert kc.count == 10

    def test_concurrent_adds_are_safe(self) -> None:
        """Multiple threads incrementing concurrently produce correct total."""
        kc = KeystrokeCounter()
        threads = [
            threading.Thread(target=lambda: [kc.add(1) for _ in range(100)])
            for _ in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert kc.count == 1000


# ---------------------------------------------------------------------------
# _get_session_log_path
# ---------------------------------------------------------------------------


class TestGetSessionLogPath:
    def test_path_is_inside_sessions_dir(self) -> None:
        p = _get_session_log_path("claude")
        sessions_dir = Path.home() / ".local" / "share" / "dictare" / "sessions"
        assert p.parent == sessions_dir

    def test_filename_contains_agent_id(self) -> None:
        p = _get_session_log_path("myagent")
        assert "myagent" in p.name

    def test_filename_contains_version(self) -> None:
        p = _get_session_log_path("test")
        assert __version__ in p.name

    def test_filename_ends_with_jsonl(self) -> None:
        p = _get_session_log_path("test")
        assert p.suffix == ".jsonl"

    def test_filename_has_timestamp_prefix(self) -> None:
        """Filename starts with YYYY-MM-DD_HH-MM-SS format."""
        import re
        p = _get_session_log_path("test")
        assert re.match(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_", p.name)

    def test_different_agent_ids_differ(self) -> None:
        p1 = _get_session_log_path("claude")
        p2 = _get_session_log_path("cursor")
        assert p1.name != p2.name


# ---------------------------------------------------------------------------
# _write_session_start / _write_session_end
# ---------------------------------------------------------------------------


class TestWriteSessionStart:
    def test_writes_valid_json_line(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _write_session_start(p, "claude", ["claude", "--fast"], "http://localhost:8770")
        line = p.read_text().strip()
        data = json.loads(line)
        assert data["event"] == "session_start"

    def test_contains_required_fields(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _write_session_start(p, "claude", ["claude"], "http://localhost:8770")
        data = json.loads(p.read_text().strip())
        for field in ("agent_id", "command", "base_url", "dictare_version", "timestamp"):
            assert field in data, f"Missing field: {field}"

    def test_agent_id_written(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _write_session_start(p, "myagent", ["myagent"], "http://localhost:8770")
        data = json.loads(p.read_text().strip())
        assert data["agent_id"] == "myagent"

    def test_command_written(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _write_session_start(p, "test", ["claude", "--model", "opus"], "http://localhost:8770")
        data = json.loads(p.read_text().strip())
        assert data["command"] == ["claude", "--model", "opus"]

    def test_version_matches(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _write_session_start(p, "test", ["cmd"], "http://localhost:8770")
        data = json.loads(p.read_text().strip())
        assert data["dictare_version"] == __version__


class TestWriteSessionEnd:
    def test_writes_session_end_event(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _write_session_end(p, exit_code=0)
        data = json.loads(p.read_text().strip())
        assert data["event"] == "session_end"

    def test_exit_code_written(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _write_session_end(p, exit_code=42)
        data = json.loads(p.read_text().strip())
        assert data["exit_code"] == 42

    def test_total_keystrokes_written(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _write_session_end(p, exit_code=0, total_keystrokes=150)
        data = json.loads(p.read_text().strip())
        assert data["total_keystrokes"] == 150

    def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _write_session_start(p, "test", ["cmd"], "http://localhost:8770")
        _write_session_end(p, exit_code=0)
        lines = p.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "session_start"
        assert json.loads(lines[1])["event"] == "session_end"


# ---------------------------------------------------------------------------
# _log_event
# ---------------------------------------------------------------------------


class TestLogEvent:
    def test_writes_event_with_ts(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _log_event(p, "my_event", {"key": "value"})
        data = json.loads(p.read_text().strip())
        assert data["event"] == "my_event"
        assert "ts" in data
        assert data["key"] == "value"

    def test_data_merged_into_entry(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _log_event(p, "msg_read", {"seq": 3, "text": "hello"})
        data = json.loads(p.read_text().strip())
        assert data["seq"] == 3
        assert data["text"] == "hello"

    def test_appends_multiple_events(self, tmp_path: Path) -> None:
        p = tmp_path / "session.jsonl"
        _log_event(p, "e1", {"a": 1})
        _log_event(p, "e2", {"b": 2})
        lines = p.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "e1"
        assert json.loads(lines[1])["event"] == "e2"

    def test_oserror_does_not_raise(self, tmp_path: Path) -> None:
        """If the file cannot be written, _log_event silently ignores the error."""
        bad_path = tmp_path / "no_such_dir" / "session.jsonl"
        # Should not raise even though parent dir doesn't exist
        _log_event(bad_path, "event", {"x": 1})


# ---------------------------------------------------------------------------
# _write_all
# ---------------------------------------------------------------------------


class TestWriteAll:
    def test_single_write_returns_total_bytes(self) -> None:
        writes: list[bytes] = []

        def fake_write(fd: int, data: bytes) -> int:
            writes.append(data)
            return len(data)

        with patch("os.write", side_effect=fake_write):
            result = _write_all(99, b"hello world")

        assert result == 11
        assert writes == [b"hello world"]

    def test_short_write_loops_until_done(self) -> None:
        """Simulate an os.write that only writes 3 bytes at a time."""
        write_calls: list[bytes] = []

        def fake_write(fd: int, data: bytes) -> int:
            chunk = data[:3]
            write_calls.append(chunk)
            return len(chunk)

        with patch("os.write", side_effect=fake_write):
            result = _write_all(99, b"abcdefghi")

        assert result == 9
        assert b"".join(write_calls) == b"abcdefghi"

    def test_zero_return_raises_oserror(self) -> None:
        """os.write returning 0 should raise OSError."""
        def fake_write(fd: int, data: bytes) -> int:
            return 0

        with patch("os.write", side_effect=fake_write):
            with pytest.raises(OSError, match="returned 0"):
                _write_all(99, b"data")

    def test_empty_data_returns_zero(self) -> None:
        with patch("os.write") as mock_write:
            result = _write_all(99, b"")
        assert result == 0
        mock_write.assert_not_called()

    def test_returns_correct_total_on_partial_writes(self) -> None:
        """Total bytes returned matches input length regardless of chunk sizes."""
        call_sizes = [5, 3, 2]  # 10 bytes total in 3 writes
        idx = [0]

        def fake_write(fd: int, data: bytes) -> int:
            n = min(call_sizes[idx[0]], len(data))
            idx[0] += 1
            return n

        with patch("os.write", side_effect=fake_write):
            result = _write_all(99, b"a" * 10)

        assert result == 10
