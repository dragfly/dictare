"""Tests for JSONL structured logger (dictare.logging.jsonl)."""

from __future__ import annotations

import json
from pathlib import Path

from dictare.logging.jsonl import JSONLLogger, LogLevel, get_default_log_path

# ---------------------------------------------------------------------------
# LogLevel enum
# ---------------------------------------------------------------------------

class TestLogLevel:
    def test_error_is_lowest(self) -> None:
        assert LogLevel.ERROR < LogLevel.INFO < LogLevel.DEBUG

    def test_names(self) -> None:
        assert LogLevel.ERROR.name == "ERROR"
        assert LogLevel.INFO.name == "INFO"
        assert LogLevel.DEBUG.name == "DEBUG"

    def test_values(self) -> None:
        assert LogLevel.ERROR == 10
        assert LogLevel.INFO == 20
        assert LogLevel.DEBUG == 30


# ---------------------------------------------------------------------------
# get_default_log_path
# ---------------------------------------------------------------------------

class TestGetDefaultLogPath:
    def test_default_name(self) -> None:
        path = get_default_log_path()
        assert path.name == "listen.jsonl"

    def test_custom_name(self) -> None:
        path = get_default_log_path("agent.myagent")
        assert path.name == "agent.myagent.jsonl"

    def test_path_in_logs_dir(self) -> None:
        path = get_default_log_path("engine")
        assert path.parent.name == "logs"


# ---------------------------------------------------------------------------
# JSONLLogger — basics
# ---------------------------------------------------------------------------

class TestJSONLLoggerBasics:
    def test_session_start_logged(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        logger = JSONLLogger(log_path, version="1.0.0")
        logger.close()

        lines = log_path.read_text().strip().splitlines()
        first = json.loads(lines[0])
        assert first["event"] == "session_start"
        assert first["version"] == "1.0.0"
        assert first["level"] == "INFO"

    def test_session_end_logged_on_close(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        logger = JSONLLogger(log_path, version="1.0.0")
        logger.close()

        lines = log_path.read_text().strip().splitlines()
        last = json.loads(lines[-1])
        assert last["event"] == "session_end"

    def test_context_manager(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0") as logger:
            logger.log("test_event")

        lines = log_path.read_text().strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        assert "session_start" in events
        assert "test_event" in events
        assert "session_end" in events

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        log_path = tmp_path / "deep" / "nested" / "test.jsonl"
        logger = JSONLLogger(log_path, version="1.0.0")
        logger.close()
        assert log_path.exists()

    def test_startup_params_in_session_start(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        logger = JSONLLogger(log_path, version="1.0.0", params={"mode": "test"})
        logger.close()

        first = json.loads(log_path.read_text().strip().splitlines()[0])
        assert first["mode"] == "test"

    def test_double_close_is_safe(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        logger = JSONLLogger(log_path, version="1.0.0")
        logger.close()
        logger.close()  # Should not raise


# ---------------------------------------------------------------------------
# Log levels
# ---------------------------------------------------------------------------

class TestJSONLLoggerLevels:
    def test_log_at_info_level(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0", level=LogLevel.INFO) as logger:
            logger.log("info_event")
            logger.debug("debug_event")
            logger.error("error_event")

        lines = log_path.read_text().strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        assert "info_event" in events
        assert "error_event" in events
        assert "debug_event" not in events  # filtered out

    def test_log_at_debug_level(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0", level=LogLevel.DEBUG) as logger:
            logger.log("info_event")
            logger.debug("debug_event")
            logger.error("error_event")

        lines = log_path.read_text().strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        assert "info_event" in events
        assert "debug_event" in events
        assert "error_event" in events

    def test_log_at_error_level(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0", level=LogLevel.ERROR) as logger:
            logger.log("info_event")
            logger.debug("debug_event")
            logger.error("error_event")

        lines = log_path.read_text().strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        # session_start is INFO which is > ERROR, so filtered
        assert "info_event" not in events
        assert "debug_event" not in events
        assert "error_event" in events


# ---------------------------------------------------------------------------
# Specialized log methods
# ---------------------------------------------------------------------------

class TestJSONLLoggerTranscription:
    def test_transcription_metadata(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0") as logger:
            logger.log_transcription("hello world", duration_ms=1500, language="en", stt_ms=200.123)

        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[-2])  # before session_end
        assert entry["event"] == "transcription"
        assert entry["chars"] == 11
        assert entry["words"] == 2
        assert entry["duration_ms"] == 1500
        assert entry["stt_ms"] == 200.1
        assert entry["language"] == "en"
        assert "text" not in entry  # not verbose

    def test_transcription_verbose_includes_text(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0", params={"verbose": True}) as logger:
            logger.log_transcription("hello world")

        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[-2])
        assert entry["text"] == "hello world"


class TestJSONLLoggerCommand:
    def test_command_metadata(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0") as logger:
            logger.log_command("mute", intent="mute", confidence=0.95, executed=True)

        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[-2])
        assert entry["event"] == "command"
        assert entry["intent"] == "mute"
        assert entry["confidence"] == 0.95
        assert entry["executed"] is True

    def test_command_debug_includes_text(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0", level=LogLevel.DEBUG) as logger:
            logger.log_command("ok mute", intent="mute", confidence=0.9, executed=True)

        lines = log_path.read_text().strip().splitlines()
        events = {json.loads(line)["event"]: json.loads(line) for line in lines}
        assert "command_text" in events
        assert events["command_text"]["text"] == "ok mute"


class TestJSONLLoggerStateChange:
    def test_state_change(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0", level=LogLevel.DEBUG) as logger:
            logger.log_state_change("off", "listening", "hotkey")

        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[-2])
        assert entry["event"] == "state_change"
        assert entry["old_state"] == "off"
        assert entry["new_state"] == "listening"
        assert entry["trigger"] == "hotkey"


class TestJSONLLoggerInjection:
    def test_injection_metadata(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0") as logger:
            logger.log_injection(
                "hello",
                method="ydotool",
                success=True,
                auto_submit=True,
                enter_sent=True,
                submit_trigger="ok send",
                submit_confidence=0.9,
                inject_ms=15.789,
            )

        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[-2])
        assert entry["event"] == "injection"
        assert entry["chars"] == 5
        assert entry["method"] == "ydotool"
        assert entry["success"] is True
        assert entry["auto_submit"] is True
        assert entry["enter_sent"] is True
        assert entry["submit_trigger"] == "ok send"
        assert entry["submit_confidence"] == 0.9
        assert entry["inject_ms"] == 15.8
        assert "text" not in entry

    def test_injection_verbose_includes_text(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0", params={"verbose": True}) as logger:
            logger.log_injection("hello", method="ydotool", success=True)

        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[-2])
        assert entry["text"] == "hello"


class TestJSONLLoggerVadEvent:
    def test_vad_event(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0", level=LogLevel.DEBUG) as logger:
            logger.log_vad_event("speech_start", duration_ms=500)

        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[-2])
        assert entry["event"] == "vad"
        assert entry["type"] == "speech_start"
        assert entry["duration_ms"] == 500


class TestJSONLLoggerWakeWord:
    def test_wake_word_check(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0", level=LogLevel.DEBUG) as logger:
            logger.log_wake_word_check(
                text="hey dictare do something",
                wake_word="dictare",
                found=True,
                separator=",",
                filtered_text="do something",
            )

        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[-2])
        assert entry["event"] == "wake_word_check"
        assert entry["found"] is True
        assert entry["filtered_text"] == "do something"


class TestJSONLLoggerError:
    def test_log_error(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0") as logger:
            logger.log_error("Something broke", context="audio_capture")

        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[-2])
        assert entry["event"] == "error"
        assert entry["error"] == "Something broke"
        assert entry["context"] == "audio_capture"


# ---------------------------------------------------------------------------
# Timestamp format
# ---------------------------------------------------------------------------

class TestJSONLLoggerTimestamp:
    def test_timestamp_is_iso_format(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        with JSONLLogger(log_path, version="1.0.0") as logger:
            logger.log("test")

        lines = log_path.read_text().strip().splitlines()
        entry = json.loads(lines[0])
        ts = entry["ts"]
        # ISO format: YYYY-MM-DDTHH:MM:SS
        assert "T" in ts
