"""Tests for TapDetector state machine."""

import threading
import time

from dictare.hotkey.tap_detector import TapDetector, TapState


def _wait_until(predicate, timeout: float = 2.0) -> None:
    """Poll until predicate is true (1ms interval)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.001)

class TestTapDetectorStates:
    """Test state transitions."""

    def test_initial_state_is_idle(self):
        detector = TapDetector()
        assert detector.state == TapState.IDLE

    def test_key_down_transitions_to_pressed_1(self):
        detector = TapDetector()
        detector.on_key_down()
        assert detector.state == TapState.PRESSED_1

    def test_key_up_after_down_transitions_to_released_1(self):
        detector = TapDetector()
        detector.on_key_down()
        detector.on_key_up()
        assert detector.state == TapState.RELEASED_1

    def test_second_key_down_transitions_to_pressed_2(self):
        detector = TapDetector()
        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        assert detector.state == TapState.PRESSED_2

    def test_double_tap_resets_to_idle(self):
        detector = TapDetector()
        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        detector.on_key_up()
        assert detector.state == TapState.IDLE

class TestSingleTap:
    """Test single tap detection."""

    def test_single_tap_fires_callback(self):
        result = []
        detector = TapDetector(
            threshold=0.01,
            on_single_tap=lambda: result.append("single"),
        )

        detector.on_key_down()
        detector.on_key_up()

        _wait_until(lambda: len(result) > 0)

        assert result == ["single"]
        assert detector.state == TapState.IDLE

    def test_single_tap_not_fired_if_double_tap(self):
        result = []
        detector = TapDetector(
            threshold=0.5,
            on_single_tap=lambda: result.append("single"),
            on_double_tap=lambda: result.append("double"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        detector.on_key_up()

        # Double tap fires immediately, give a tiny margin
        _wait_until(lambda: len(result) > 0)

        assert result == ["double"]

class TestDoubleTap:
    """Test double tap detection."""

    def test_double_tap_fires_callback(self):
        result = []
        detector = TapDetector(
            threshold=0.2,
            on_double_tap=lambda: result.append("double"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        detector.on_key_up()

        assert result == ["double"]
        assert detector.state == TapState.IDLE

    def test_double_tap_fires_immediately_on_second_release(self):
        result = []
        fired_at = []

        def on_double():
            result.append("double")
            fired_at.append(time.time())

        detector = TapDetector(threshold=0.5, on_double_tap=on_double)

        start = time.time()
        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        detector.on_key_up()

        assert result == ["double"]
        # Should fire immediately, not after threshold
        assert fired_at[0] - start < 0.1

class TestDoubleTapAndHold:
    """Test double-tap-and-hold detection."""

    def test_hold_fires_callback_on_key_up(self):
        """Tap → tap-and-hold → on_hold fires on release."""
        result = []
        detector = TapDetector(
            threshold=0.5,
            hold_threshold=0.02,
            on_single_tap=lambda: result.append("single"),
            on_double_tap=lambda: result.append("double"),
            on_hold=lambda: result.append("hold"),
        )

        # First tap
        detector.on_key_down()
        detector.on_key_up()

        # Second press and hold
        detector.on_key_down()
        _wait_until(lambda: detector.state == TapState.HOLD_ACTIVE)
        assert result == []  # Armed but not fired yet

        detector.on_key_up()
        assert result == ["hold"]
        assert detector.state == TapState.IDLE

    def test_hold_not_fired_on_quick_double_tap(self):
        """Quick double-tap fires on_double_tap, not on_hold."""
        result = []
        detector = TapDetector(
            threshold=0.5,
            hold_threshold=0.5,  # Long hold threshold
            on_double_tap=lambda: result.append("double"),
            on_hold=lambda: result.append("hold"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        detector.on_key_up()  # Released before hold threshold

        assert result == ["double"]

    def test_hold_arms_state(self):
        """Verify HOLD_ACTIVE state after hold timer fires."""
        detector = TapDetector(
            threshold=0.5,
            hold_threshold=0.02,
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()

        _wait_until(lambda: detector.state == TapState.HOLD_ACTIVE)
        assert detector.state == TapState.HOLD_ACTIVE

    def test_hold_combo_aborts(self):
        """Combo during second press aborts hold and double-tap."""
        result = []
        detector = TapDetector(
            threshold=0.5,
            hold_threshold=0.02,
            on_double_tap=lambda: result.append("double"),
            on_hold=lambda: result.append("hold"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        detector.on_other_key()  # Combo detected
        detector.on_key_up()

        time.sleep(0.05)  # Wait past hold threshold
        assert result == []
        assert detector.state == TapState.IDLE

    def test_single_hold_does_not_fire_hold(self):
        """Single press-and-hold results in single tap, NOT hold."""
        result = []
        detector = TapDetector(
            threshold=0.01,
            hold_threshold=0.02,
            on_single_tap=lambda: result.append("single"),
            on_hold=lambda: result.append("hold"),
        )

        # Single press and hold — no hold timer since it's the first press
        detector.on_key_down()
        time.sleep(0.05)  # Hold well past thresholds
        detector.on_key_up()

        _wait_until(lambda: len(result) > 0)
        assert result == ["single"]

    def test_hold_active_in_valid_transitions(self):
        """HOLD_ACTIVE state is in the transition dict."""
        assert TapState.HOLD_ACTIVE in TapDetector.VALID_TRANSITIONS
        assert TapDetector.VALID_TRANSITIONS[TapState.HOLD_ACTIVE] == [TapState.IDLE]

class TestComboAbort:
    """Test that combos (Command+Plus) abort tap detection."""

    def test_other_key_during_press_aborts_tap(self):
        result = []
        detector = TapDetector(
            threshold=0.01,
            on_single_tap=lambda: result.append("single"),
        )

        detector.on_key_down()
        detector.on_other_key()  # Another key pressed while hotkey down
        detector.on_key_up()

        # Wait for the short timer to expire — should NOT fire
        _wait_until(lambda: detector.state == TapState.IDLE)

        assert result == []  # No tap fired
        assert detector.state == TapState.IDLE

    def test_other_key_during_second_press_aborts_double_tap(self):
        result = []
        detector = TapDetector(
            threshold=0.01,
            on_single_tap=lambda: result.append("single"),
            on_double_tap=lambda: result.append("double"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        detector.on_other_key()  # Combo detected on second press
        detector.on_key_up()

        _wait_until(lambda: detector.state == TapState.IDLE)

        # Neither single nor double should fire
        assert result == []
        assert detector.state == TapState.IDLE

    def test_other_key_after_release_does_not_affect(self):
        """Other key pressed after release doesn't abort."""
        result = []
        detector = TapDetector(
            threshold=0.01,
            on_single_tap=lambda: result.append("single"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.on_other_key()  # After release, shouldn't matter

        _wait_until(lambda: len(result) > 0)

        assert result == ["single"]

class TestKeyRepeat:
    """Test that key repeat is handled correctly."""

    def test_repeated_key_down_ignored(self):
        detector = TapDetector()

        detector.on_key_down()
        detector.on_key_down()  # Repeat
        detector.on_key_down()  # Repeat

        assert detector.state == TapState.PRESSED_1

    def test_spurious_key_up_ignored(self):
        detector = TapDetector()

        detector.on_key_up()  # No prior down

        assert detector.state == TapState.IDLE

class TestReset:
    """Test reset functionality."""

    def test_reset_returns_to_idle(self):
        detector = TapDetector()

        detector.on_key_down()
        detector.on_key_up()
        assert detector.state == TapState.RELEASED_1

        detector.reset()
        assert detector.state == TapState.IDLE

    def test_reset_cancels_timer(self):
        result = []
        detector = TapDetector(
            threshold=0.01,
            on_single_tap=lambda: result.append("single"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.reset()

        # Wait longer than threshold to confirm timer was cancelled
        time.sleep(0.03)

        assert result == []  # Timer was cancelled

class TestThreadSafety:
    """Test thread safety."""

    def test_concurrent_events(self):
        """Multiple threads sending events shouldn't crash."""
        result = []
        detector = TapDetector(
            threshold=0.01,
            on_single_tap=lambda: result.append("single"),
            on_double_tap=lambda: result.append("double"),
        )

        def spam_events():
            for _ in range(100):
                detector.on_key_down()
                detector.on_key_up()
                detector.on_other_key()

        threads = [threading.Thread(target=spam_events) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not crash, state should be valid
        assert detector.state in TapState

class TestValidTransitions:
    """Test VALID_TRANSITIONS dict matches actual behavior."""

    def test_all_states_have_transitions(self):
        for state in TapState:
            assert state in TapDetector.VALID_TRANSITIONS

    def test_idle_can_only_go_to_pressed_1(self):
        assert TapDetector.VALID_TRANSITIONS[TapState.IDLE] == [TapState.PRESSED_1]

    def test_pressed_1_can_go_to_released_1_or_idle(self):
        transitions = TapDetector.VALID_TRANSITIONS[TapState.PRESSED_1]
        assert TapState.RELEASED_1 in transitions
        assert TapState.IDLE in transitions

    def test_released_1_can_go_to_pressed_2_or_idle(self):
        transitions = TapDetector.VALID_TRANSITIONS[TapState.RELEASED_1]
        assert TapState.PRESSED_2 in transitions
        assert TapState.IDLE in transitions

    def test_pressed_2_can_go_to_hold_active_or_idle(self):
        transitions = TapDetector.VALID_TRANSITIONS[TapState.PRESSED_2]
        assert TapState.HOLD_ACTIVE in transitions
        assert TapState.IDLE in transitions

class TestSimulatedTap:
    """Test simulated taps (SIGUSR1 path).

    On macOS the Swift launcher sends SIGUSR1 for each tap. The Python
    handler simulates a complete tap via on_key_down() + on_key_up().
    Two SIGUSR1 within the threshold should trigger double-tap.
    """

    def test_simulated_single_tap(self):
        """One key_down+key_up pair fires single tap after timeout."""
        result: list[str] = []
        detector = TapDetector(
            threshold=0.01,
            on_single_tap=lambda: result.append("single"),
            on_double_tap=lambda: result.append("double"),
        )

        # Simulate SIGUSR1: complete tap
        detector.on_key_down()
        detector.on_key_up()

        _wait_until(lambda: len(result) > 0)
        assert result == ["single"]

    def test_simulated_double_tap(self):
        """Two rapid key_down+key_up pairs fire double tap."""
        result: list[str] = []
        detector = TapDetector(
            threshold=0.5,
            on_single_tap=lambda: result.append("single"),
            on_double_tap=lambda: result.append("double"),
        )

        # Simulate two SIGUSR1 in rapid succession
        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        detector.on_key_up()

        assert result == ["double"]

    def test_simulated_slow_taps_fire_two_singles(self):
        """Two taps separated by more than threshold fire two single taps."""
        result: list[str] = []
        detector = TapDetector(
            threshold=0.01,
            on_single_tap=lambda: result.append("single"),
            on_double_tap=lambda: result.append("double"),
        )

        # First tap
        detector.on_key_down()
        detector.on_key_up()

        # Wait for timeout (single tap fires)
        _wait_until(lambda: len(result) >= 1)
        assert result == ["single"]

        # Second tap (well after threshold)
        detector.on_key_down()
        detector.on_key_up()

        _wait_until(lambda: len(result) >= 2)
        assert result == ["single", "single"]
