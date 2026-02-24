"""Finite State Machine for dictare.

Contains everything that defines the FSM:
- AppState: enum of valid states
- VALID_TRANSITIONS: transition table
- StateManager: thread-safe state machine
- StateMessage and subclasses: inputs to the FSM

Messages are sent from producer threads (VAD, STT, TTS, hotkey, API) to the
single StateController consumer via a thread-safe queue.

Two categories of messages:
- Notifications (past tense): report something that happened
  (SpeechStarted, SpeechEnded, TranscriptionCompleted, PlayStarted, PlayCompleted)
- Commands (imperative): request an action
  (HotkeyPressed, SwitchAgent, SetListening, DiscardCurrent)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

# =============================================================================
# States
# =============================================================================


class AppState(Enum):
    """Application states.

    State machine:
        OFF ↔ LISTENING (hotkey toggle)
        LISTENING → RECORDING (VAD speech start)
        LISTENING → PLAYING (TTS feedback, if tts_pauses_listening=true)
        LISTENING → TRANSCRIBING (processing queued audio)
        RECORDING → TRANSCRIBING (VAD speech end)
        RECORDING → LISTENING (audio too short)
        TRANSCRIBING → INJECTING (text to inject)
        TRANSCRIBING → LISTENING (no injection)
        INJECTING → LISTENING
        PLAYING → LISTENING (TTS complete)
    """

    OFF = auto()          # Mic disabled, not listening
    LISTENING = auto()    # Mic active, waiting for speech
    RECORDING = auto()    # VAD detected speech, recording
    TRANSCRIBING = auto() # Processing audio with Whisper
    INJECTING = auto()    # Injecting text
    PLAYING = auto()      # Playing TTS feedback (mic ignored)

    def __str__(self) -> str:
        """Return human-readable state name."""
        return self.name.capitalize()


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: AppState, to_state: AppState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Invalid transition: {from_state} → {to_state}")


# =============================================================================
# State Manager (the state machine)
# =============================================================================


class StateManager:
    """Thread-safe state machine with validated transitions."""

    VALID_TRANSITIONS: dict[AppState, list[AppState]] = {
        AppState.OFF: [AppState.LISTENING],
        AppState.LISTENING: [AppState.RECORDING, AppState.TRANSCRIBING, AppState.PLAYING, AppState.OFF],
        AppState.RECORDING: [AppState.TRANSCRIBING, AppState.LISTENING, AppState.OFF],
        AppState.TRANSCRIBING: [AppState.INJECTING, AppState.LISTENING, AppState.OFF],
        AppState.INJECTING: [AppState.LISTENING, AppState.OFF],
        AppState.PLAYING: [AppState.LISTENING, AppState.OFF],
    }

    def __init__(
        self,
        initial_state: AppState = AppState.OFF,
    ) -> None:
        """Initialize state manager.

        Args:
            initial_state: Starting state (default: OFF)
        """
        self._state = initial_state
        self._lock = threading.Lock()

    @property
    def state(self) -> AppState:
        """Get current state (thread-safe read)."""
        with self._lock:
            return self._state

    @property
    def is_listening(self) -> bool:
        """Check if in LISTENING state (mic active, waiting for speech)."""
        return self.state == AppState.LISTENING

    @property
    def is_off(self) -> bool:
        """Check if in OFF state (mic disabled)."""
        return self.state == AppState.OFF

    @property
    def is_active(self) -> bool:
        """Check if actively processing (not OFF or LISTENING)."""
        return self.state not in (AppState.OFF, AppState.LISTENING)

    @property
    def should_process_audio(self) -> bool:
        """Check if audio should be processed by VAD.

        True for LISTENING, RECORDING, TRANSCRIBING, and INJECTING so that
        speech arriving during transcription is segmented and queued for
        sequential STT processing.  PLAYING and OFF remain excluded.
        """
        return self.state in (
            AppState.LISTENING,
            AppState.RECORDING,
            AppState.TRANSCRIBING,
            AppState.INJECTING,
        )

    def transition(self, to_state: AppState, *, force: bool = False) -> bool:
        """Attempt state transition.

        Args:
            to_state: Target state
            force: If True, skip validation (use sparingly)

        Returns:
            True if transition succeeded

        Raises:
            InvalidTransitionError: If transition is invalid and force=False
        """
        with self._lock:
            from_state = self._state

            # Same state = no-op
            if from_state == to_state:
                return True

            # Validate transition
            if not force:
                valid_targets = self.VALID_TRANSITIONS.get(from_state, [])
                if to_state not in valid_targets:
                    raise InvalidTransitionError(from_state, to_state)

            self._state = to_state

        return True

    def try_transition(self, to_state: AppState) -> bool:
        """Attempt state transition, returning False on invalid transition.

        Unlike transition(), this doesn't raise on invalid transitions.

        Args:
            to_state: Target state

        Returns:
            True if transition succeeded, False if invalid
        """
        try:
            return self.transition(to_state)
        except InvalidTransitionError:
            return False

    def reset_to_listening(self) -> None:
        """Force reset to LISTENING state."""
        self.transition(AppState.LISTENING, force=True)

    def can_transition_to(self, to_state: AppState) -> bool:
        """Check if transition to target state is valid from current state."""
        with self._lock:
            valid_targets = self.VALID_TRANSITIONS.get(self._state, [])
            return to_state in valid_targets

    def __str__(self) -> str:
        """Return current state as string."""
        return str(self.state)


# =============================================================================
# Messages (inputs to the FSM)
# =============================================================================


@dataclass(frozen=True)
class StateMessage:
    """Base message with timestamp and source.

    All messages are immutable (frozen=True) to ensure thread-safety.
    Messages are processed FIFO — no priority.
    """

    timestamp: float = field(default_factory=time.time)
    source: str = ""  # "vad", "stt", "tts", "hotkey", "api", etc.


# --- Notifications (past tense — something happened) ---


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


# --- Commands (imperative — request an action) ---


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
