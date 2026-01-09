"""State machine for voxtype."""

from __future__ import annotations

import threading
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable

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

class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: AppState, to_state: AppState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Invalid transition: {from_state} → {to_state}")

class StateManager:
    """Thread-safe state machine with validated transitions.

    Valid transitions:
        IDLE → RECORDING (VAD detects speech start)
        IDLE → TRANSCRIBING (processing queued audio)
        RECORDING → TRANSCRIBING (VAD detects speech end)
        RECORDING → IDLE (audio too short, discarded)
        TRANSCRIBING → INJECTING (LLM decides to inject)
        TRANSCRIBING → IDLE (transcription complete, no inject)
        INJECTING → IDLE (injection complete)
    """

    VALID_TRANSITIONS: dict[AppState, list[AppState]] = {
        AppState.IDLE: [AppState.RECORDING, AppState.TRANSCRIBING],
        AppState.RECORDING: [AppState.TRANSCRIBING, AppState.IDLE],
        AppState.TRANSCRIBING: [AppState.INJECTING, AppState.IDLE],
        AppState.INJECTING: [AppState.IDLE],
        AppState.LISTENING: [],  # LISTENING is not used in the state machine
    }

    def __init__(
        self,
        initial_state: AppState = AppState.IDLE,
        on_transition: Callable[[AppState, AppState], None] | None = None,
    ) -> None:
        """Initialize state manager.

        Args:
            initial_state: Starting state (default: IDLE)
            on_transition: Optional callback(from_state, to_state) on successful transitions
        """
        self._state = initial_state
        self._lock = threading.Lock()
        self._on_transition = on_transition

    @property
    def state(self) -> AppState:
        """Get current state (thread-safe read)."""
        with self._lock:
            return self._state

    @property
    def is_idle(self) -> bool:
        """Check if in IDLE state."""
        return self.state == AppState.IDLE

    @property
    def is_busy(self) -> bool:
        """Check if busy (not IDLE)."""
        return self.state != AppState.IDLE

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

        # Callback outside lock to prevent deadlocks
        if self._on_transition:
            self._on_transition(from_state, to_state)

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

    def reset(self) -> None:
        """Force reset to IDLE state."""
        self.transition(AppState.IDLE, force=True)

    def can_transition_to(self, to_state: AppState) -> bool:
        """Check if transition to target state is valid from current state."""
        with self._lock:
            valid_targets = self.VALID_TRANSITIONS.get(self._state, [])
            return to_state in valid_targets

    def __str__(self) -> str:
        """Return current state as string."""
        return str(self.state)
