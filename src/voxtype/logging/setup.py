"""Logging setup using standard Python logging with JSON formatter.

This module provides idiomatic Python structured logging using:
- Standard `logging` module (thread-safe, global loggers)
- `python-json-logger` for JSON formatting

Usage:
    # At app startup:
    from voxtype.logging.setup import setup_logging
    setup_logging(log_path="/path/to/log.jsonl", level=logging.INFO)

    # In any module:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("event_name", extra={"key": "value"})
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pythonjsonlogger.json import JsonFormatter

# Default log directory
DEFAULT_LOG_DIR = Path.home() / ".local" / "share" / "voxtype" / "logs"

def get_default_log_path(name: str = "listen") -> Path:
    """Get default log file path.

    Args:
        name: Log name (e.g., "listen" or "agent.myagent")

    Returns:
        Path to log file in default log directory.
    """
    return DEFAULT_LOG_DIR / f"{name}.jsonl"

class VoxtypeJsonFormatter(JsonFormatter):
    """Custom JSON formatter for voxtype logs.

    Adds:
    - ISO timestamp as 'ts'
    - Renames 'message' to 'event' for structured events
    """

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        # Add ISO timestamp
        log_record["ts"] = datetime.now(timezone.utc).isoformat()

        # Add level name
        log_record["level"] = record.levelname

        # The message becomes the event name
        if "message" in log_record:
            log_record["event"] = log_record.pop("message")

        # Add logger name for debugging
        log_record["logger"] = record.name

def setup_logging(
    log_path: Path | str | None = None,
    level: int = logging.INFO,
    version: str | None = None,
    params: dict[str, Any] | None = None,
) -> logging.Handler | None:
    """Configure logging with JSON formatter.

    Call this once at application startup. After this, any module can use:
        logger = logging.getLogger(__name__)
        logger.info("event_name", extra={"key": "value"})

    Args:
        log_path: Path to log file. If None, only console logging.
        level: Logging level (logging.DEBUG, logging.INFO, etc.)
        version: App version to log at session start.
        params: Additional params to log at session start.

    Returns:
        The file handler if log_path provided, else None.
    """
    # Configure root logger
    root_logger = logging.getLogger("voxtype")
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    handler: logging.Handler | None = None

    if log_path:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # File handler with JSON formatter
        handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(VoxtypeJsonFormatter())
        root_logger.addHandler(handler)

        # Log session start
        session_data = {"version": version} if version else {}
        if params:
            session_data.update(params)

        root_logger.info("session_start", extra=session_data)

    return handler

def shutdown_logging() -> None:
    """Shutdown logging cleanly.

    Call this at application exit to log session_end and flush handlers.
    """
    logger = logging.getLogger("voxtype")
    logger.info("session_end")
    logging.shutdown()
