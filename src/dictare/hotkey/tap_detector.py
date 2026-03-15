"""Tap detection state machine for modifier keys.

Detects single-tap, double-tap, and double-tap-and-hold on a hotkey while
ignoring key combinations (e.g., Command+Plus should not trigger a tap).

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

    PRESSED_2 ──[hold_timeout]──> HOLD_ACTIVE ──[key_up]──> IDLE
                                       (arms; fires on_hold on key_up)
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
    HOLD_ACTIVE = auto()  # Double-tap-and-hold detected, waiting for key_up

class TapDetector:
    """Detects single tap, double tap, and double-tap-and-hold on a modifier key.

    Uses same pattern as StateManager: Enum states + VALID_TRANSITIONS dict.

    Handles the case where the key is used as a modifier in a combo
    (e.g., Command+Plus) by aborting tap detection when other keys
    are pressed while the hotkey is down.

    Timer semantics:
    - key_down (first press) transitions to PRESSED_1. No timer started —
      a single long hold just results in a single tap on release.
    - key_up (from PRESSED_1) starts a double-tap window timer (default 0.4s).
      If no second press arrives, on_single_tap is called.
    - key_down (second press within window) cancels the double-tap timer
      and starts a hold timer (default 0.8s). If still held when it fires,
      transitions to HOLD_ACTIVE; on_hold fires on key_up.
    - key_up (from PRESSED_2, before hold timer) fires on_double_tap.
    """

    VALID_TRANSITIONS: dict[TapState, list[TapState]] = {
        TapState.IDLE: [TapState.PRESSED_1],
        TapState.PRESSED_1: [TapState.RELEASED_1, TapState.IDLE],
        TapState.RELEASED_1: [TapState.PRESSED_2, TapState.IDLE],
        TapState.PRESSED_2: [TapState.HOLD_ACTIVE, TapState.IDLE],
        TapState.HOLD_ACTIVE: [TapState.IDLE],
    }

    def __init__(
        self,
        threshold: float = 0.4,
        hold_threshold: float = 0.8,
        on_single_tap: Callable[[], None] | None = None,
        on_double_tap: Callable[[], None] | None = None,
        on_hold: Callable[[], None] | None = None,
    ) -> None:
        """Initialize tap detector.

        Args:
            threshold: Max seconds between taps for double-tap,
                      and delay before single-tap fires after key_up.
            hold_threshold: Seconds to hold on second press before hold fires.
            on_single_tap: Callback when single tap detected.
            on_double_tap: Callback when double tap detected.
            on_hold: Callback when double-tap-and-hold detected (fires on key_up).
        """
        self.threshold = threshold
        self.hold_threshold = hold_threshold
        self._on_single_tap = on_single_tap
        self._on_double_tap = on_double_tap
        self._on_hold = on_hold

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

            elif self._state == TapState.RELEASED_1:
                self._cancel_timer()  # Cancel double-tap window timer
                self._transition(TapState.PRESSED_2)
                self._combo_detected = False
                self._start_hold_timer()

            # PRESSED_1, PRESSED_2, HOLD_ACTIVE = key repeat, ignore

    def on_key_up(self) -> None:
        """Called when the hotkey is released."""
        callback = None

        with self._lock:
            if self._state == TapState.PRESSED_1:
                if self._combo_detected:
                    self._reset()
                else:
                    self._transition(TapState.RELEASED_1)
                    self._start_double_tap_timer()

            elif self._state == TapState.PRESSED_2:
                self._cancel_timer()  # Cancel hold timer
                if self._combo_detected:
                    self._reset()
                else:
                    callback = self._on_double_tap
                    self._reset()

            elif self._state == TapState.HOLD_ACTIVE:
                # Hold was armed; fire callback now that modifier is released.
                callback = self._on_hold
                self._reset()

        if callback:
            callback()

    def on_other_key(self) -> None:
        """Called when any other key is pressed (combo detection)."""
        with self._lock:
            if self._state in (TapState.PRESSED_1, TapState.PRESSED_2):
                self._combo_detected = True

    def _start_hold_timer(self) -> None:
        """Start hold detection timer (on second press)."""
        self._cancel_timer()
        self._timer = threading.Timer(self.hold_threshold, self._on_hold_timeout)
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

    def _on_hold_timeout(self) -> None:
        """Hold timer fired — key still held on second press. Arms the hold."""
        with self._lock:
            if self._state == TapState.PRESSED_2 and not self._combo_detected:
                self._state = TapState.HOLD_ACTIVE
                self._timer = None

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
