"""JSONL (newline-delimited JSON) structured logger."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

class JSONLLogger:
    """Structured logger that writes JSONL format.

    Each log entry is a JSON object on a single line, making it easy
    to parse and analyze programmatically.

    Example output:
    {"ts":"2024-12-30T10:30:00Z","event":"transcription","text":"hello world",...}
    {"ts":"2024-12-30T10:30:01Z","event":"wake_word_check","found":true,...}
    """

    def __init__(self, log_path: Path | str, version: str) -> None:
        """Initialize the JSONL logger.

        Args:
            log_path: Path to the log file.
            version: Application version for logging.
        """
        self.log_path = Path(log_path)
        self.version = version
        self._file = None

        # Ensure parent directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Open file in append mode
        self._file = open(self.log_path, "a", encoding="utf-8")

        # Log session start
        self.log("session_start", version=version)

    def log(self, event: str, **data: Any) -> None:
        """Log an event with structured data.

        Args:
            event: Event type (e.g., "transcription", "command", "state_change").
            **data: Additional key-value data to include.
        """
        if not self._file:
            return

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **data,
        }

        try:
            self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._file.flush()  # Ensure immediate write
        except Exception:
            pass  # Don't crash on logging errors

    def log_transcription(
        self,
        text: str,
        duration_ms: Optional[float] = None,
        language: Optional[str] = None,
    ) -> None:
        """Log a transcription event."""
        self.log(
            "transcription",
            text=text,
            duration_ms=duration_ms,
            language=language,
        )

    def log_wake_word_check(
        self,
        text: str,
        wake_word: str,
        found: bool,
        separator: Optional[str] = None,
        filtered_text: Optional[str] = None,
    ) -> None:
        """Log a wake word check."""
        self.log(
            "wake_word_check",
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
        self.log(
            "command",
            text=text,
            intent=intent,
            confidence=confidence,
            executed=executed,
        )

    def log_state_change(
        self,
        old_state: str,
        new_state: str,
        trigger: str,
    ) -> None:
        """Log a state change."""
        self.log(
            "state_change",
            old_state=old_state,
            new_state=new_state,
            trigger=trigger,
        )

    def log_injection(
        self,
        text: str,
        method: str,
        success: bool,
    ) -> None:
        """Log a text injection."""
        self.log(
            "injection",
            text=text[:100],  # Truncate for log size
            method=method,
            success=success,
        )

    def log_vad_event(
        self,
        event_type: str,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Log a VAD event (speech start/end)."""
        self.log(
            "vad",
            type=event_type,
            duration_ms=duration_ms,
        )

    def log_error(self, error: str, context: Optional[str] = None) -> None:
        """Log an error."""
        self.log(
            "error",
            error=error,
            context=context,
        )

    def close(self) -> None:
        """Close the log file."""
        if self._file:
            self.log("session_end")
            self._file.close()
            self._file = None

    def __enter__(self) -> "JSONLLogger":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
