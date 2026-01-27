"""Tap detection state machine for modifier keys.

Detects single-tap and double-tap on a hotkey while ignoring
key combinations (e.g., Command+Plus should not trigger a tap).

State machine:
    IDLE ──[key_down]──> KEY_DOWN_1 ──[key_up]──> WAITING_SECOND
                              │                        │
                        [other_key]               [key_down]
                              │                        │
                              v                        v
                            IDLE                  KEY_DOWN_2 ──[key_up]──> DOUBLE_TAP
                                                       │
                                                 [other_key]
                                                       │
                                                       v
                                                     IDLE

    WAITING_SECOND ──[timeout]──> SINGLE_TAP

Usage:
    detector = TapDetector(
        threshold=0.4,
        on_single_tap=lambda: print("single"),
        on_double_tap=lambda: print("double"),
    )

    listener.start(
        on_press=detector.on_key_down,
        on_release=detector.on_key_up,
        on_other_key=detector.on_other_key,
    )
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TapDetector:
    """Detects single and double taps on a modifier key.

    Handles the case where the key is used as a modifier in a combo
    (e.g., Command+Plus) by aborting tap detection when other keys
    are pressed while the hotkey is down.
    """

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

        # State
        self._key_is_down = False
        self._tap_count = 0  # 0, 1, or 2 completed taps
        self._combo_detected = False
        self._first_down_time: float = 0.0
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_key_down(self) -> None:
        """Called when the hotkey is pressed down."""
        with self._lock:
            if self._key_is_down:
                # Key repeat, ignore
                return

            self._key_is_down = True
            self._combo_detected = False

            if self._tap_count == 0:
                # First press: start tracking
                self._first_down_time = time.time()
                self._start_timer()
            # If tap_count == 1, this is second press (potential double tap)

    def on_key_up(self) -> None:
        """Called when the hotkey is released."""
        callback = None

        with self._lock:
            if not self._key_is_down:
                # Spurious release, ignore
                return

            self._key_is_down = False

            # If combo was detected (other key pressed), abort
            if self._combo_detected:
                self._reset_state()
                return

            # Complete a tap
            self._tap_count += 1

            if self._tap_count >= 2:
                # Double tap complete
                self._cancel_timer()
                callback = self._on_double_tap
                self._reset_state()

            # If tap_count == 1, wait for timer or second tap

        # Call outside lock
        if callback:
            callback()

    def on_other_key(self) -> None:
        """Called when any other key is pressed.

        If the hotkey is currently down, marks it as a combo
        and the tap will be aborted on release.
        """
        with self._lock:
            if self._key_is_down:
                self._combo_detected = True

    def _start_timer(self) -> None:
        """Start the timeout timer."""
        self._cancel_timer()
        self._timer = threading.Timer(self.threshold, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self) -> None:
        """Cancel the timeout timer if running."""
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _on_timeout(self) -> None:
        """Timer fired - if one tap completed, trigger single tap."""
        callback = None

        with self._lock:
            if self._tap_count == 1 and not self._combo_detected and not self._key_is_down:
                callback = self._on_single_tap
            self._reset_state()

        # Call outside lock
        if callback:
            callback()

    def _reset_state(self) -> None:
        """Reset all state. Must be called with lock held."""
        self._key_is_down = False
        self._tap_count = 0
        self._combo_detected = False
        self._first_down_time = 0.0
        self._cancel_timer()

    def reset(self) -> None:
        """Public reset for cleanup."""
        with self._lock:
            self._reset_state()
