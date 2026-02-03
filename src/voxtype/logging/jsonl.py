"""JSONL (newline-delimited JSON) structured logger with log levels."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any

class LogLevel(IntEnum):
    """Log levels for structured logging."""

    ERROR = 10
    INFO = 20
    DEBUG = 30

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

class JSONLLogger:
    """Structured logger that writes JSONL format with log levels.

    Each log entry is a JSON object on a single line, making it easy
    to parse and analyze programmatically.

    Log levels control what is logged:
    - ERROR: Only errors
    - INFO: Metadata only (counts, durations) - no text content for privacy
    - DEBUG: Everything including text content

    Example output (INFO level):
    {"ts":"2024-12-30T10:30:00Z","level":"INFO","event":"transcription","chars":12,"duration_ms":1500}

    Example output (DEBUG level):
    {"ts":"2024-12-30T10:30:00Z","level":"DEBUG","event":"transcription","text":"hello world","chars":11,"duration_ms":1500}
    """

    def __init__(
        self,
        log_path: Path | str,
        version: str,
        level: LogLevel = LogLevel.INFO,
        params: dict | None = None,
    ) -> None:
        """Initialize the JSONL logger.

        Args:
            log_path: Path to the log file.
            version: Application version for logging.
            level: Log level (ERROR, INFO, DEBUG).
            params: Optional startup parameters to log.
        """
        self.log_path = Path(log_path)
        self.version = version
        self.level = level
        self._file = None

        # Ensure parent directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Open file in append mode
        self._file = open(self.log_path, "a", encoding="utf-8")

        # Log session start with all parameters
        session_data = {"version": version}
        if params:
            session_data.update(params)
        self._log_internal("session_start", LogLevel.INFO, **session_data)

    def _log_internal(self, event: str, level: LogLevel, **data: Any) -> None:
        """Internal log method with level.

        Args:
            event: Event type (e.g., "transcription", "command", "state_change").
            level: Log level for this event.
            **data: Additional key-value data to include.
        """
        if not self._file or level > self.level:
            return

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level.name,
            "event": event,
            **data,
        }

        try:
            self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._file.flush()  # Ensure immediate write
        except Exception:
            pass  # Don't crash on logging errors

    def log(self, event: str, **data: Any) -> None:
        """Log an event at INFO level.

        Args:
            event: Event type (e.g., "transcription", "command", "state_change").
            **data: Additional key-value data to include.
        """
        self._log_internal(event, LogLevel.INFO, **data)

    def debug(self, event: str, **data: Any) -> None:
        """Log an event at DEBUG level.

        Args:
            event: Event type.
            **data: Additional key-value data to include.
        """
        self._log_internal(event, LogLevel.DEBUG, **data)

    def error(self, event: str, **data: Any) -> None:
        """Log an event at ERROR level.

        Args:
            event: Event type.
            **data: Additional key-value data to include.
        """
        self._log_internal(event, LogLevel.ERROR, **data)

    def log_transcription(
        self,
        text: str,
        duration_ms: float | None = None,
        language: str | None = None,
    ) -> None:
        """Log a transcription event.

        At INFO level: logs only metadata (chars, word count, duration)
        At DEBUG level: also logs the actual text
        """
        chars = len(text)
        words = len(text.split())

        # INFO level: metadata only (privacy)
        self._log_internal(
            "transcription",
            LogLevel.INFO,
            chars=chars,
            words=words,
            duration_ms=duration_ms,
            language=language,
        )

        # DEBUG level: include text content
        if self.level >= LogLevel.DEBUG:
            self._log_internal(
                "transcription_text",
                LogLevel.DEBUG,
                text=text,
            )

    def log_wake_word_check(
        self,
        text: str,
        wake_word: str,
        found: bool,
        separator: str | None = None,
        filtered_text: str | None = None,
    ) -> None:
        """Log a wake word check."""
        # Always log at DEBUG (contains text)
        self._log_internal(
            "wake_word_check",
            LogLevel.DEBUG,
            text=text,
            wake_word=wake_word,
            found=found,
            separator=separator,
            filtered_text=filtered_text,
        )

    def log_command(
        self,
        text: str,
        intent: str,
        confidence: float,
        executed: bool,
    ) -> None:
        """Log a command classification/execution."""
        # INFO: metadata only
        self._log_internal(
            "command",
            LogLevel.INFO,
            intent=intent,
            confidence=confidence,
            executed=executed,
        )
        # DEBUG: include text
        if self.level >= LogLevel.DEBUG:
            self._log_internal(
                "command_text",
                LogLevel.DEBUG,
                text=text,
            )

    def log_state_change(
        self,
        old_state: str,
        new_state: str,
        trigger: str,
    ) -> None:
        """Log a state change."""
        self._log_internal(
            "state_change",
            LogLevel.DEBUG,
            old_state=old_state,
            new_state=new_state,
            trigger=trigger,
        )

    def log_injection(
        self,
        text: str,
        method: str,
        success: bool,
        auto_enter: bool = False,
        enter_sent: bool | None = None,
        submit_trigger: str | None = None,
        submit_confidence: float | None = None,
    ) -> None:
        """Log a text injection."""
        chars = len(text)
        # INFO: metadata only
        extra: dict = {
            "chars": chars,
            "method": method,
            "success": success,
            "auto_enter": auto_enter,
            "enter_sent": enter_sent,
        }
        # Add trigger info if submit was triggered by voice
        if submit_trigger:
            extra["submit_trigger"] = submit_trigger
            extra["submit_confidence"] = submit_confidence
        self._log_internal("injection", LogLevel.INFO, **extra)
        # DEBUG: include text
        if self.level >= LogLevel.DEBUG:
            self._log_internal(
                "injection_text",
                LogLevel.DEBUG,
                text=text,
            )

    def log_vad_event(
        self,
        event_type: str,
        duration_ms: float | None = None,
    ) -> None:
        """Log a VAD event (speech start/end)."""
        self._log_internal(
            "vad",
            LogLevel.DEBUG,
            type=event_type,
            duration_ms=duration_ms,
        )

    def log_error(self, error: str, context: str | None = None) -> None:
        """Log an error."""
        self._log_internal(
            "error",
            LogLevel.ERROR,
            error=error,
            context=context,
        )

    def close(self) -> None:
        """Close the log file."""
        if self._file:
            self._log_internal("session_end", LogLevel.INFO)
            self._file.close()
            self._file = None

    def __enter__(self) -> JSONLLogger:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
