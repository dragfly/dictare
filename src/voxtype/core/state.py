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
    ERROR = auto()

    def __str__(self) -> str:
        """Return human-readable state name."""
        return self.name.capitalize()
