"""Tests for the idiomatic Python logging setup."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from voxtype.logging.setup import (
    VoxtypeJsonFormatter,
    get_default_log_path,
    setup_logging,
    shutdown_logging,
)

class TestGetDefaultLogPath:
    """Tests for get_default_log_path."""

    def test_default_name(self):
        """Default name is 'listen'."""
        path = get_default_log_path()
        assert path.name == "listen.jsonl"
        assert ".local/share/voxtype/logs" in str(path)

    def test_custom_name(self):
        """Custom name is used."""
        path = get_default_log_path("agent.myagent")
        assert path.name == "agent.myagent.jsonl"

class TestVoxtypeJsonFormatter:
    """Tests for VoxtypeJsonFormatter."""

    def test_format_includes_required_fields(self):
        """Formatted log includes ts, level, event, logger."""
        formatter = VoxtypeJsonFormatter()

        # Create a log record
        record = logging.LogRecord(
            name="voxtype.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test_event",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert "ts" in data
        assert data["level"] == "INFO"
        assert data["event"] == "test_event"
        assert data["logger"] == "voxtype.test"

    def test_extra_fields_included(self):
        """Extra fields from record are included."""
        formatter = VoxtypeJsonFormatter()

        record = logging.LogRecord(
            name="voxtype.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test_event",
            args=(),
            exc_info=None,
        )
        record.custom_field = "custom_value"
        record.count = 42

        output = formatter.format(record)
        data = json.loads(output)

        assert data["custom_field"] == "custom_value"
        assert data["count"] == 42

class TestSetupLogging:
    """Tests for setup_logging."""

    def test_setup_returns_handler_with_path(self):
        """setup_logging returns handler when log_path provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.jsonl"
            handler = setup_logging(log_path=log_path)

            assert handler is not None
            assert isinstance(handler, logging.FileHandler)

            # Cleanup
            handler.close()
            logging.getLogger("voxtype").handlers.clear()

    def test_setup_returns_none_without_path(self):
        """setup_logging returns None when no log_path."""
        handler = setup_logging(log_path=None)
        assert handler is None
        logging.getLogger("voxtype").handlers.clear()

    def test_logging_writes_to_file(self):
        """Log messages are written to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.jsonl"
            handler = setup_logging(log_path=log_path, level=logging.DEBUG)

            # Log a message
            logger = logging.getLogger("voxtype.test")
            logger.info("test_event", extra={"key": "value"})

            # Flush
            handler.flush()

            # Read and verify
            content = log_path.read_text()
            lines = content.strip().split("\n")

            # Should have session_start + our message
            assert len(lines) >= 2

            # Check our message
            data = json.loads(lines[-1])
            assert data["event"] == "test_event"
            assert data["key"] == "value"

            # Cleanup
            handler.close()
            logging.getLogger("voxtype").handlers.clear()

    def test_session_start_logged(self):
        """session_start is logged at setup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.jsonl"
            handler = setup_logging(
                log_path=log_path,
                version="1.2.3",
                params={"mode": "test"},
            )
            handler.flush()

            content = log_path.read_text()
            lines = content.strip().split("\n")

            # First line should be session_start
            data = json.loads(lines[0])
            assert data["event"] == "session_start"
            assert data["version"] == "1.2.3"
            assert data["mode"] == "test"

            # Cleanup
            handler.close()
            logging.getLogger("voxtype").handlers.clear()

    def test_creates_parent_directories(self):
        """setup_logging creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "nested" / "deep" / "test.jsonl"
            handler = setup_logging(log_path=log_path)

            assert log_path.parent.exists()

            # Cleanup
            handler.close()
            logging.getLogger("voxtype").handlers.clear()

class TestShutdownLogging:
    """Tests for shutdown_logging."""

    def test_logs_session_end(self):
        """shutdown_logging logs session_end."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.jsonl"
            setup_logging(log_path=log_path)

            shutdown_logging()

            content = log_path.read_text()
            lines = content.strip().split("\n")

            # Last line should be session_end
            data = json.loads(lines[-1])
            assert data["event"] == "session_end"

            # Note: shutdown_logging closes handlers, so no manual cleanup needed

class TestModuleLogger:
    """Tests for module-level logger pattern."""

    def test_module_logger_pattern(self):
        """Module can use logging.getLogger(__name__) pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.jsonl"
            handler = setup_logging(log_path=log_path)

            # This is the pattern used in modules
            logger = logging.getLogger("voxtype.pipeline.submit_filter")
            logger.info("submit_trigger", extra={
                "pattern": ["ok", "invia"],
                "matched_tokens": ["ok", "invia"],
                "confidence": 0.95,
            })

            handler.flush()

            content = log_path.read_text()
            lines = content.strip().split("\n")

            # Find our message
            found = False
            for line in lines:
                data = json.loads(line)
                if data.get("event") == "submit_trigger":
                    assert data["pattern"] == ["ok", "invia"]
                    assert data["confidence"] == 0.95
                    assert data["logger"] == "voxtype.pipeline.submit_filter"
                    found = True
                    break

            assert found, "submit_trigger event not found"

            # Cleanup
            handler.close()
            logging.getLogger("voxtype").handlers.clear()
