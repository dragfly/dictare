"""State machine for voxtype."""

from __future__ import annotations

from enum import Enum, auto


class AppState(Enum):
    """Application states."""

    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    INJECTING = auto()
    LISTENING = auto()  # Continuous transcription mode (no wake word needed)

    def __str__(self) -> str:
        """Return human-readable state name."""
        return self.name.capitalize()


class ProcessingMode(Enum):
    """Processing modes for transcribed text."""

    TRANSCRIPTION = "transcription"  # Direct transcription, no LLM
    COMMAND = "command"  # LLM-based command processing

    def __str__(self) -> str:
        """Return human-readable mode name."""
        return self.name.capitalize()
