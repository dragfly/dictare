"""Tests for log viewing CLI helpers (dictare.cli.logs)."""

from __future__ import annotations

import json

from dictare.cli.logs import (
    LEVEL_COLORS,
    _format_entry,
    _format_line,
    _matches_source,
    _parse_line,
)

# ---------------------------------------------------------------------------
# _parse_line
# ---------------------------------------------------------------------------

class TestParseLine:
    def test_valid_json(self) -> None:
        line = json.dumps({"event": "test", "level": "INFO"})
        result = _parse_line(line)
        assert result is not None
        assert result["event"] == "test"

    def test_blank_line(self) -> None:
        assert _parse_line("") is None
        assert _parse_line("   ") is None
        assert _parse_line("\n") is None

    def test_non_json_passthrough(self) -> None:
        result = _parse_line("some plain text")
        assert result is not None
        assert result["event"] == "some plain text"

    def test_whitespace_stripped(self) -> None:
        line = "  " + json.dumps({"event": "test"}) + "  "
        result = _parse_line(line)
        assert result is not None
        assert result["event"] == "test"


# ---------------------------------------------------------------------------
# _matches_source
# ---------------------------------------------------------------------------

class TestMatchesSource:
    def test_empty_filter_matches_everything(self) -> None:
        assert _matches_source({"source": "engine"}, "") is True
        assert _matches_source({}, "") is True

    def test_matching_source(self) -> None:
        assert _matches_source({"source": "engine"}, "engine") is True

    def test_non_matching_source(self) -> None:
        assert _matches_source({"source": "engine"}, "tray") is False

    def test_missing_source_field(self) -> None:
        assert _matches_source({}, "engine") is False


# ---------------------------------------------------------------------------
# _format_entry
# ---------------------------------------------------------------------------

class TestFormatEntry:
    def test_basic_format(self) -> None:
        entry = {
            "ts": "2025-01-15T10:30:45.123456+00:00",
            "level": "INFO",
            "event": "session_start",
        }
        result = _format_entry(entry)
        assert "10:30:45" in result
        assert "INFO" in result
        assert "session_start" in result

    def test_timestamp_shortened_to_time(self) -> None:
        entry = {
            "ts": "2025-01-15T14:22:33.000+00:00",
            "level": "DEBUG",
            "event": "test",
        }
        result = _format_entry(entry)
        assert "14:22:33" in result
        assert "2025" not in result

    def test_logger_short_name(self) -> None:
        entry = {
            "ts": "",
            "level": "INFO",
            "event": "test",
            "logger": "dictare.pipeline.submit_filter",
        }
        result = _format_entry(entry)
        assert "[submit_filter]" in result

    def test_source_shown(self) -> None:
        entry = {
            "ts": "",
            "level": "INFO",
            "event": "test",
            "source": "tray",
        }
        result = _format_entry(entry)
        assert "<tray>" in result

    def test_extras_shown(self) -> None:
        entry = {
            "ts": "",
            "level": "INFO",
            "event": "test",
            "chars": 42,
            "duration_ms": 1500,
        }
        result = _format_entry(entry)
        assert "chars=42" in result
        assert "duration_ms=1500" in result

    def test_known_fields_excluded_from_extras(self) -> None:
        entry = {
            "ts": "2025-01-15T10:30:45",
            "level": "INFO",
            "event": "test",
            "logger": "dictare.test",
            "version": "1.0.0",
            "pid": 12345,
            "source": "engine",
        }
        result = _format_entry(entry)
        # Known fields should not appear in extras
        assert "version=" not in result
        assert "pid=" not in result

    def test_none_values_excluded(self) -> None:
        entry = {
            "ts": "",
            "level": "INFO",
            "event": "test",
            "optional_field": None,
        }
        result = _format_entry(entry)
        assert "optional_field" not in result

    def test_missing_event_uses_message(self) -> None:
        entry = {
            "ts": "",
            "level": "INFO",
            "message": "fallback message",
        }
        result = _format_entry(entry)
        assert "fallback message" in result

    def test_level_padded(self) -> None:
        entry = {"ts": "", "level": "info", "event": "test"}
        result = _format_entry(entry)
        assert "INFO" in result


# ---------------------------------------------------------------------------
# _format_line
# ---------------------------------------------------------------------------

class TestFormatLine:
    def test_valid_json_line(self) -> None:
        line = json.dumps({"ts": "", "level": "INFO", "event": "hello"})
        result = _format_line(line)
        assert result is not None
        assert "hello" in result

    def test_blank_line_returns_none(self) -> None:
        assert _format_line("") is None

    def test_source_filter_applied(self) -> None:
        line = json.dumps({"event": "test", "source": "engine"})
        assert _format_line(line, source_filter="engine") is not None
        assert _format_line(line, source_filter="tray") is None


# ---------------------------------------------------------------------------
# LEVEL_COLORS
# ---------------------------------------------------------------------------

class TestLevelColors:
    def test_all_levels_have_colors(self) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            assert level in LEVEL_COLORS
