"""Tap detection state machine for modifier keys.

Detects single-tap and double-tap on a hotkey while ignoring
key combinations (e.g., Command+Plus should not trigger a tap).

State machine (same pattern as core/state.py):

    IDLE ──[key_down]──> PRESSED_1 ──[key_up]──> RELEASED_1
                              │                      │
                        [other_key]             [key_down]
                              │                      │
                              v                      v
                            IDLE               PRESSED_2 ──[key_up]──> DOUBLE_TAP → IDLE
                                                    │
                                              [other_key]
                                                    │
                                                    v
                                                  IDLE

    RELEASED_1 ──[timeout]──> SINGLE_TAP → IDLE
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from enum import Enum, auto


class TapState(Enum):
    """Tap detector states."""

    IDLE = auto()        # Waiting for key press
    PRESSED_1 = auto()   # First press, key is down
    RELEASED_1 = auto()  # First tap complete, waiting for second
    PRESSED_2 = auto()   # Second press, key is down


class TapDetector:
    """Detects single and double taps on a modifier key.

    Uses same pattern as StateManager: Enum states + VALID_TRANSITIONS dict.

    Handles the case where the key is used as a modifier in a combo
    (e.g., Command+Plus) by aborting tap detection when other keys
    are pressed while the hotkey is down.
    """

    VALID_TRANSITIONS: dict[TapState, list[TapState]] = {
        TapState.IDLE: [TapState.PRESSED_1],
        TapState.PRESSED_1: [TapState.RELEASED_1, TapState.IDLE],  # IDLE = abort on combo
        TapState.RELEASED_1: [TapState.PRESSED_2, TapState.IDLE],  # IDLE = timeout/single tap
        TapState.PRESSED_2: [TapState.IDLE],  # IDLE = double tap or abort
    }

    def __init__(
        self,
        threshold: float = 0.4,
        on_single_tap: Callable[[], None] | None = None,
        on_double_tap: Callable[[], None] | None = None,
    ) -> None:
        """Initialize tap detector.

        Args:
            threshold: Max seconds between taps for double-tap,
                      and delay before single-tap fires.
            on_single_tap: Callback when single tap detected.
            on_double_tap: Callback when double tap detected.
        """
        self.threshold = threshold
        self._on_single_tap = on_single_tap
        self._on_double_tap = on_double_tap

        self._state = TapState.IDLE
        self._combo_detected = False
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> TapState:
        """Current state (thread-safe)."""
        with self._lock:
            return self._state

    def _transition(self, to_state: TapState) -> bool:
        """Attempt state transition. Returns True if valid."""
        valid = self.VALID_TRANSITIONS.get(self._state, [])
        if to_state not in valid:
            return False
        self._state = to_state
        return True

    def on_key_down(self) -> None:
        """Called when the hotkey is pressed down."""
        with self._lock:
            if self._state == TapState.IDLE:
                self._transition(TapState.PRESSED_1)
                self._combo_detected = False
                self._start_timer()

            elif self._state == TapState.RELEASED_1:
                self._transition(TapState.PRESSED_2)
                self._combo_detected = False

            # PRESSED_1 or PRESSED_2 = key repeat, ignore

    def on_key_up(self) -> None:
        """Called when the hotkey is released."""
        callback = None

        with self._lock:
            if self._state == TapState.PRESSED_1:
                if self._combo_detected:
                    self._reset()
                else:
                    self._transition(TapState.RELEASED_1)

            elif self._state == TapState.PRESSED_2:
                self._cancel_timer()
                if self._combo_detected:
                    self._reset()
                else:
                    callback = self._on_double_tap
                    self._reset()

        if callback:
            callback()

    def on_other_key(self) -> None:
        """Called when any other key is pressed (combo detection)."""
        with self._lock:
            if self._state in (TapState.PRESSED_1, TapState.PRESSED_2):
                self._combo_detected = True

    def _start_timer(self) -> None:
        """Start timeout timer."""
        self._cancel_timer()
        self._timer = threading.Timer(self.threshold, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self) -> None:
        """Cancel timeout timer."""
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _on_timeout(self) -> None:
        """Timer fired - single tap if in RELEASED_1 state."""
        callback = None

        with self._lock:
            if self._state == TapState.RELEASED_1 and not self._combo_detected:
                callback = self._on_single_tap
            self._reset()

        if callback:
            callback()

    def _reset(self) -> None:
        """Reset to IDLE. Must hold lock."""
        self._state = TapState.IDLE
        self._combo_detected = False
        self._cancel_timer()

    def reset(self) -> None:
        """Public reset for cleanup."""
        with self._lock:
            self._reset()
