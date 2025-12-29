"""State machine for claude-mic."""

from __future__ import annotations

from enum import Enum, auto

class AppState(Enum):
    """Application states."""

    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    INJECTING = auto()
    ERROR = auto()

    def __str__(self) -> str:
        """Return human-readable state name."""
        return self.name.capitalize()
