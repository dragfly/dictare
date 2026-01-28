"""Tests for TapDetector state machine."""

import threading
import time

from voxtype.hotkey.tap_detector import TapDetector, TapState

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
            threshold=0.1,
            on_single_tap=lambda: result.append("single"),
        )

        detector.on_key_down()
        detector.on_key_up()

        # Wait for timer
        time.sleep(0.15)

        assert result == ["single"]
        assert detector.state == TapState.IDLE

    def test_single_tap_not_fired_if_double_tap(self):
        result = []
        detector = TapDetector(
            threshold=0.2,
            on_single_tap=lambda: result.append("single"),
            on_double_tap=lambda: result.append("double"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        detector.on_key_up()

        # Wait for potential timer
        time.sleep(0.25)

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

class TestComboAbort:
    """Test that combos (Command+Plus) abort tap detection."""

    def test_other_key_during_press_aborts_tap(self):
        result = []
        detector = TapDetector(
            threshold=0.1,
            on_single_tap=lambda: result.append("single"),
        )

        detector.on_key_down()
        detector.on_other_key()  # Another key pressed while hotkey down
        detector.on_key_up()

        time.sleep(0.15)

        assert result == []  # No tap fired
        assert detector.state == TapState.IDLE

    def test_other_key_during_second_press_aborts_double_tap(self):
        result = []
        detector = TapDetector(
            threshold=0.2,
            on_single_tap=lambda: result.append("single"),
            on_double_tap=lambda: result.append("double"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.on_key_down()
        detector.on_other_key()  # Combo detected on second press
        detector.on_key_up()

        time.sleep(0.25)

        # Neither single nor double should fire
        assert result == []
        assert detector.state == TapState.IDLE

    def test_other_key_after_release_does_not_affect(self):
        """Other key pressed after release doesn't abort."""
        result = []
        detector = TapDetector(
            threshold=0.1,
            on_single_tap=lambda: result.append("single"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.on_other_key()  # After release, shouldn't matter

        time.sleep(0.15)

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
            threshold=0.1,
            on_single_tap=lambda: result.append("single"),
        )

        detector.on_key_down()
        detector.on_key_up()
        detector.reset()

        time.sleep(0.15)

        assert result == []  # Timer was cancelled

class TestThreadSafety:
    """Test thread safety."""

    def test_concurrent_events(self):
        """Multiple threads sending events shouldn't crash."""
        result = []
        detector = TapDetector(
            threshold=0.05,
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

    def test_pressed_2_can_only_go_to_idle(self):
        assert TapDetector.VALID_TRANSITIONS[TapState.PRESSED_2] == [TapState.IDLE]
