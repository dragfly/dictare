"""Messages for the state machine (StateController).

These are the inputs to the FSM event queue. They are NOT domain events —
they are thread-safe messages sent from producer threads (VAD, STT, TTS,
hotkey, API) to the single StateController consumer.

Two categories:
- Notifications (past tense): report something that happened
  (SpeechStarted, SpeechEnded, TranscriptionCompleted, PlayStarted, PlayCompleted)
- Commands (imperative): request an action
  (HotkeyPressed, SwitchAgent, SetListening, DiscardCurrent)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class StateMessage:
    """Base message with timestamp and source.

    All messages are immutable (frozen=True) to ensure thread-safety.
    Messages are processed FIFO — no priority.
    """

    timestamp: float = field(default_factory=time.time)
    source: str = ""  # "vad", "stt", "tts", "hotkey", "api", etc.

# =============================================================================
# Notifications (past tense — something happened)
# =============================================================================

@dataclass(frozen=True)
class SpeechStarted(StateMessage):
    """VAD detected speech start."""

    pass

@dataclass(frozen=True)
class SpeechEnded(StateMessage):
    """VAD detected speech end.

    Captures audio_data and agent at creation time,
    ensuring they go to the correct agent even if agent switches later.
    """

    audio_data: Any = None
    agent: Any = None  # Captured at creation time

@dataclass(frozen=True)
class TranscriptionCompleted(StateMessage):
    """STT finished transcribing."""

    text: str = ""
    agent: Any = None  # The agent to use for injection
    language: str | None = None  # Detected language from STT

@dataclass(frozen=True)
class PlayStarted(StateMessage):
    """TTS playback starting.

    Each TTS start increments a counter. The play_id is assigned by the controller
    when the message is processed, not when it's created.
    """

    text: str = ""

@dataclass(frozen=True)
class PlayCompleted(StateMessage):
    """TTS playback finished.

    The play_id must match the ID assigned when PlayStarted was processed.
    If multiple TTS are playing concurrently, only the completion of the
    LAST started TTS will trigger state transition back to LISTENING.
    """

    play_id: int = 0  # Must match the ID from PlayStarted

# =============================================================================
# Commands (imperative — request an action)
# =============================================================================

@dataclass(frozen=True)
class HotkeyPressed(StateMessage):
    """User pressed hotkey to toggle listening."""

    pass

@dataclass(frozen=True)
class SwitchAgent(StateMessage):
    """User wants to switch agent."""

    direction: int = 1  # +1 next, -1 prev
    agent_name: str | None = None  # If switching by name
    agent_index: int | None = None  # If switching by index (1-based)

@dataclass(frozen=True)
class SetListening(StateMessage):
    """API request to set listening on/off."""

    on: bool = True

@dataclass(frozen=True)
class DiscardCurrent(StateMessage):
    """User wants to discard current recording."""

    pass
