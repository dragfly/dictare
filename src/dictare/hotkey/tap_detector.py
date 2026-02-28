"""Tap detection state machine for modifier keys.

Detects single-tap, double-tap, and long-press on a hotkey while ignoring
key combinations (e.g., Command+Plus should not trigger a tap).

State machine:

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

    RELEASED_1 ──[double_tap_timeout]──> SINGLE_TAP → IDLE

    PRESSED_1 ──[long_press_timeout]──> LONG_PRESSED ──[key_up]──> IDLE
                                             (fires on_long_press immediately)
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from enum import Enum, auto


class TapState(Enum):
    """Tap detector states."""

    IDLE = auto()          # Waiting for key press
    PRESSED_1 = auto()    # First press, key is down
    RELEASED_1 = auto()   # First tap complete, waiting for second
    PRESSED_2 = auto()    # Second press, key is down
    LONG_PRESSED = auto()  # Long press detected, waiting for key_up


class TapDetector:
    """Detects single tap, double tap, and long press on a modifier key.

    Uses same pattern as StateManager: Enum states + VALID_TRANSITIONS dict.

    Handles the case where the key is used as a modifier in a combo
    (e.g., Command+Plus) by aborting tap detection when other keys
    are pressed while the hotkey is down.

    Timer semantics:
    - key_down starts a long-press timer (default 0.8s).
      If the key is still held when it fires, on_long_press is called.
    - key_up (before long-press fires) cancels that timer and starts a
      double-tap window timer (default 0.4s).
      If no second press arrives, on_single_tap is called.
    """

    VALID_TRANSITIONS: dict[TapState, list[TapState]] = {
        TapState.IDLE: [TapState.PRESSED_1],
        TapState.PRESSED_1: [TapState.RELEASED_1, TapState.LONG_PRESSED, TapState.IDLE],
        TapState.RELEASED_1: [TapState.PRESSED_2, TapState.IDLE],
        TapState.PRESSED_2: [TapState.IDLE],
        TapState.LONG_PRESSED: [TapState.IDLE],
    }

    def __init__(
        self,
        threshold: float = 0.4,
        long_press_threshold: float = 0.8,
        on_single_tap: Callable[[], None] | None = None,
        on_double_tap: Callable[[], None] | None = None,
        on_long_press: Callable[[], None] | None = None,
    ) -> None:
        """Initialize tap detector.

        Args:
            threshold: Max seconds between taps for double-tap,
                      and delay before single-tap fires after key_up.
            long_press_threshold: Seconds to hold before long-press fires.
            on_single_tap: Callback when single tap detected.
            on_double_tap: Callback when double tap detected.
            on_long_press: Callback when long press detected (fires while key held).
        """
        self.threshold = threshold
        self.long_press_threshold = long_press_threshold
        self._on_single_tap = on_single_tap
        self._on_double_tap = on_double_tap
        self._on_long_press = on_long_press

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
                self._start_long_press_timer()

            elif self._state == TapState.RELEASED_1:
                self._cancel_timer()  # Cancel double-tap window timer
                self._transition(TapState.PRESSED_2)
                self._combo_detected = False

            # PRESSED_1, PRESSED_2, LONG_PRESSED = key repeat, ignore

    def on_key_up(self) -> None:
        """Called when the hotkey is released."""
        callback = None

        with self._lock:
            if self._state == TapState.PRESSED_1:
                self._cancel_timer()  # Cancel long-press timer
                if self._combo_detected:
                    self._reset()
                else:
                    self._transition(TapState.RELEASED_1)
                    self._start_double_tap_timer()

            elif self._state == TapState.PRESSED_2:
                self._cancel_timer()
                if self._combo_detected:
                    self._reset()
                else:
                    callback = self._on_double_tap
                    self._reset()

            elif self._state == TapState.LONG_PRESSED:
                # Long press already fired; just reset on key_up
                self._reset()

        if callback:
            callback()

    def on_other_key(self) -> None:
        """Called when any other key is pressed (combo detection)."""
        with self._lock:
            if self._state in (TapState.PRESSED_1, TapState.PRESSED_2):
                self._combo_detected = True

    def _start_long_press_timer(self) -> None:
        """Start long-press detection timer."""
        self._cancel_timer()
        self._timer = threading.Timer(self.long_press_threshold, self._on_long_press_timeout)
        self._timer.daemon = True
        self._timer.start()

    def _start_double_tap_timer(self) -> None:
        """Start double-tap window timer."""
        self._cancel_timer()
        self._timer = threading.Timer(self.threshold, self._on_double_tap_timeout)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self) -> None:
        """Cancel active timer."""
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _on_long_press_timeout(self) -> None:
        """Long-press timer fired — key still held."""
        callback = None

        with self._lock:
            if self._state == TapState.PRESSED_1 and not self._combo_detected:
                callback = self._on_long_press
                # Don't reset — stay in LONG_PRESSED until key_up
                self._state = TapState.LONG_PRESSED
                self._timer = None

        if callback:
            callback()

    def _on_double_tap_timeout(self) -> None:
        """Double-tap window expired — fire single tap."""
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
