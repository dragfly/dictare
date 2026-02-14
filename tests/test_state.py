"""Tests for state machine."""

import threading
import time

import pytest

from voxtype.core.state import (
    AppState,
    InvalidTransitionError,
    StateManager,
)

class TestAppState:
    """Test AppState enum."""

    def test_all_states_exist(self) -> None:
        """Verify all expected states are defined."""
        assert AppState.OFF
        assert AppState.LISTENING
        assert AppState.RECORDING
        assert AppState.TRANSCRIBING
        assert AppState.INJECTING
        assert AppState.PLAYING

    def test_str_returns_capitalized_name(self) -> None:
        """Test __str__ returns capitalized state name."""
        assert str(AppState.OFF) == "Off"
        assert str(AppState.LISTENING) == "Listening"
        assert str(AppState.RECORDING) == "Recording"
        assert str(AppState.TRANSCRIBING) == "Transcribing"

class TestInvalidTransitionError:
    """Test InvalidTransitionError exception."""

    def test_error_contains_states(self) -> None:
        """Test error message contains both states."""
        error = InvalidTransitionError(AppState.OFF, AppState.INJECTING)
        assert error.from_state == AppState.OFF
        assert error.to_state == AppState.INJECTING
        # State names are capitalized in str()
        assert "Off" in str(error)
        assert "Injecting" in str(error)

class TestStateManagerBasics:
    """Test basic StateManager operations."""

    def test_initial_state_is_off(self) -> None:
        """Test default initial state is OFF."""
        sm = StateManager()
        assert sm.state == AppState.OFF

    def test_custom_initial_state(self) -> None:
        """Test custom initial state."""
        sm = StateManager(initial_state=AppState.RECORDING)
        assert sm.state == AppState.RECORDING

    def test_is_off_property(self) -> None:
        """Test is_off property."""
        sm = StateManager()
        assert sm.is_off is True
        sm.transition(AppState.LISTENING)
        assert sm.is_off is False

    def test_is_listening_property(self) -> None:
        """Test is_listening property."""
        sm = StateManager()
        assert sm.is_listening is False
        sm.transition(AppState.LISTENING)
        assert sm.is_listening is True

    def test_should_process_audio_true_for_listening_and_recording(self) -> None:
        """VAD runs only in LISTENING and RECORDING."""
        for state in (AppState.LISTENING, AppState.RECORDING):
            sm = StateManager(initial_state=state)
            assert sm.should_process_audio is True, f"Expected True for {state}"

    def test_should_process_audio_false_for_other_states(self) -> None:
        """VAD does not run in OFF, TRANSCRIBING, INJECTING, PLAYING."""
        for state in (AppState.OFF, AppState.TRANSCRIBING,
                      AppState.INJECTING, AppState.PLAYING):
            sm = StateManager(initial_state=state)
            assert sm.should_process_audio is False, f"Expected False for {state}"

    def test_is_active_property(self) -> None:
        """Test is_active property."""
        sm = StateManager(initial_state=AppState.LISTENING)
        assert sm.is_active is False
        sm.transition(AppState.RECORDING)
        assert sm.is_active is True

    def test_str_returns_state_name(self) -> None:
        """Test __str__ returns current state."""
        sm = StateManager()
        assert str(sm) == "Off"

class TestValidTransitions:
    """Test valid state transitions."""

    def test_off_to_listening(self) -> None:
        """OFF → LISTENING is valid (hotkey toggle)."""
        sm = StateManager()
        result = sm.transition(AppState.LISTENING)
        assert result is True
        assert sm.state == AppState.LISTENING

    def test_listening_to_recording(self) -> None:
        """LISTENING → RECORDING is valid (VAD speech start)."""
        sm = StateManager(initial_state=AppState.LISTENING)
        result = sm.transition(AppState.RECORDING)
        assert result is True
        assert sm.state == AppState.RECORDING

    def test_listening_to_transcribing(self) -> None:
        """LISTENING → TRANSCRIBING is valid (queued audio processing)."""
        sm = StateManager(initial_state=AppState.LISTENING)
        result = sm.transition(AppState.TRANSCRIBING)
        assert result is True
        assert sm.state == AppState.TRANSCRIBING

    def test_listening_to_off(self) -> None:
        """LISTENING → OFF is valid (hotkey toggle)."""
        sm = StateManager(initial_state=AppState.LISTENING)
        result = sm.transition(AppState.OFF)
        assert result is True
        assert sm.state == AppState.OFF

    def test_recording_to_transcribing(self) -> None:
        """RECORDING → TRANSCRIBING is valid (VAD speech end)."""
        sm = StateManager(initial_state=AppState.RECORDING)
        result = sm.transition(AppState.TRANSCRIBING)
        assert result is True
        assert sm.state == AppState.TRANSCRIBING

    def test_recording_to_listening(self) -> None:
        """RECORDING → LISTENING is valid (audio too short)."""
        sm = StateManager(initial_state=AppState.RECORDING)
        result = sm.transition(AppState.LISTENING)
        assert result is True
        assert sm.state == AppState.LISTENING

    def test_transcribing_to_injecting(self) -> None:
        """TRANSCRIBING → INJECTING is valid (LLM decides to inject)."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        result = sm.transition(AppState.INJECTING)
        assert result is True
        assert sm.state == AppState.INJECTING

    def test_transcribing_to_listening(self) -> None:
        """TRANSCRIBING → LISTENING is valid (no injection needed)."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        result = sm.transition(AppState.LISTENING)
        assert result is True
        assert sm.state == AppState.LISTENING

    def test_injecting_to_listening(self) -> None:
        """INJECTING → LISTENING is valid (injection complete)."""
        sm = StateManager(initial_state=AppState.INJECTING)
        result = sm.transition(AppState.LISTENING)
        assert result is True
        assert sm.state == AppState.LISTENING

    def test_same_state_transition_is_noop(self) -> None:
        """Transition to same state succeeds as no-op."""
        sm = StateManager()
        result = sm.transition(AppState.OFF)
        assert result is True
        assert sm.state == AppState.OFF

    def test_listening_to_playing(self) -> None:
        """LISTENING → PLAYING is valid (TTS audio feedback)."""
        sm = StateManager(initial_state=AppState.LISTENING)
        result = sm.transition(AppState.PLAYING)
        assert result is True
        assert sm.state == AppState.PLAYING

    def test_playing_to_listening(self) -> None:
        """PLAYING → LISTENING is valid (TTS complete)."""
        sm = StateManager(initial_state=AppState.PLAYING)
        result = sm.transition(AppState.LISTENING)
        assert result is True
        assert sm.state == AppState.LISTENING

class TestInvalidTransitions:
    """Test invalid state transitions."""

    def test_off_to_injecting_raises(self) -> None:
        """OFF → INJECTING is invalid."""
        sm = StateManager()
        with pytest.raises(InvalidTransitionError) as exc_info:
            sm.transition(AppState.INJECTING)
        assert exc_info.value.from_state == AppState.OFF
        assert exc_info.value.to_state == AppState.INJECTING
        # State should not change
        assert sm.state == AppState.OFF

    def test_off_to_recording_raises(self) -> None:
        """OFF → RECORDING is invalid (must go through LISTENING)."""
        sm = StateManager()
        with pytest.raises(InvalidTransitionError):
            sm.transition(AppState.RECORDING)
        assert sm.state == AppState.OFF

    def test_recording_to_injecting_raises(self) -> None:
        """RECORDING → INJECTING is invalid (must transcribe first)."""
        sm = StateManager(initial_state=AppState.RECORDING)
        with pytest.raises(InvalidTransitionError):
            sm.transition(AppState.INJECTING)
        assert sm.state == AppState.RECORDING

    def test_transcribing_to_recording_raises(self) -> None:
        """TRANSCRIBING → RECORDING is invalid."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        with pytest.raises(InvalidTransitionError):
            sm.transition(AppState.RECORDING)
        assert sm.state == AppState.TRANSCRIBING

    def test_injecting_to_recording_raises(self) -> None:
        """INJECTING → RECORDING is invalid."""
        sm = StateManager(initial_state=AppState.INJECTING)
        with pytest.raises(InvalidTransitionError):
            sm.transition(AppState.RECORDING)
        assert sm.state == AppState.INJECTING

    def test_injecting_to_transcribing_raises(self) -> None:
        """INJECTING → TRANSCRIBING is invalid."""
        sm = StateManager(initial_state=AppState.INJECTING)
        with pytest.raises(InvalidTransitionError):
            sm.transition(AppState.TRANSCRIBING)
        assert sm.state == AppState.INJECTING

    def test_playing_to_recording_raises(self) -> None:
        """PLAYING → RECORDING is invalid (must return to LISTENING first)."""
        sm = StateManager(initial_state=AppState.PLAYING)
        with pytest.raises(InvalidTransitionError):
            sm.transition(AppState.RECORDING)
        assert sm.state == AppState.PLAYING

    def test_recording_to_playing_raises(self) -> None:
        """RECORDING → PLAYING is invalid (can't interrupt recording)."""
        sm = StateManager(initial_state=AppState.RECORDING)
        with pytest.raises(InvalidTransitionError):
            sm.transition(AppState.PLAYING)
        assert sm.state == AppState.RECORDING

class TestTryTransition:
    """Test try_transition (non-raising version)."""

    def test_valid_transition_returns_true(self) -> None:
        """Valid transition returns True."""
        sm = StateManager(initial_state=AppState.LISTENING)
        result = sm.try_transition(AppState.RECORDING)
        assert result is True
        assert sm.state == AppState.RECORDING

    def test_invalid_transition_returns_false(self) -> None:
        """Invalid transition returns False without raising."""
        sm = StateManager()
        result = sm.try_transition(AppState.INJECTING)
        assert result is False
        assert sm.state == AppState.OFF  # State unchanged

class TestCanTransitionTo:
    """Test can_transition_to validation."""

    def test_can_transition_to_valid_state(self) -> None:
        """Returns True for valid transitions."""
        sm = StateManager(initial_state=AppState.LISTENING)
        assert sm.can_transition_to(AppState.RECORDING) is True
        assert sm.can_transition_to(AppState.TRANSCRIBING) is True

    def test_cannot_transition_to_invalid_state(self) -> None:
        """Returns False for invalid transitions."""
        sm = StateManager()
        assert sm.can_transition_to(AppState.INJECTING) is False
        assert sm.can_transition_to(AppState.RECORDING) is False

class TestForceTransition:
    """Test force=True transitions."""

    def test_force_allows_invalid_transition(self) -> None:
        """Force=True allows normally invalid transitions."""
        sm = StateManager()
        # OFF → INJECTING is normally invalid
        result = sm.transition(AppState.INJECTING, force=True)
        assert result is True
        assert sm.state == AppState.INJECTING

    def test_reset_to_listening_forces_to_listening(self) -> None:
        """reset_to_listening forces transition to LISTENING from any state."""
        sm = StateManager(initial_state=AppState.INJECTING)
        sm.reset_to_listening()
        assert sm.state == AppState.LISTENING

class TestTransitionCallback:
    """Test on_transition callback."""

    def test_callback_called_on_transition(self) -> None:
        """Callback is called with from/to states."""
        transitions = []

        def on_transition(from_state, to_state):
            transitions.append((from_state, to_state))

        sm = StateManager(initial_state=AppState.LISTENING, on_transition=on_transition)
        sm.transition(AppState.RECORDING)
        sm.transition(AppState.TRANSCRIBING)

        assert len(transitions) == 2
        assert transitions[0] == (AppState.LISTENING, AppState.RECORDING)
        assert transitions[1] == (AppState.RECORDING, AppState.TRANSCRIBING)

    def test_callback_not_called_on_same_state(self) -> None:
        """Callback is not called for same-state transition."""
        transitions = []

        def on_transition(from_state, to_state):
            transitions.append((from_state, to_state))

        sm = StateManager(on_transition=on_transition)
        sm.transition(AppState.OFF)  # Same state

        assert len(transitions) == 0

    def test_callback_not_called_on_invalid_transition(self) -> None:
        """Callback is not called when transition fails."""
        transitions = []

        def on_transition(from_state, to_state):
            transitions.append((from_state, to_state))

        sm = StateManager(on_transition=on_transition)
        with pytest.raises(InvalidTransitionError):
            sm.transition(AppState.INJECTING)

        assert len(transitions) == 0

class TestFullWorkflow:
    """Test complete state machine workflows."""

    def test_normal_transcription_workflow(self) -> None:
        """Test: OFF → LISTENING → RECORDING → TRANSCRIBING → LISTENING."""
        sm = StateManager()

        # Hotkey enables listening
        sm.transition(AppState.LISTENING)
        assert sm.state == AppState.LISTENING

        # VAD detects speech
        sm.transition(AppState.RECORDING)
        assert sm.state == AppState.RECORDING

        # VAD detects speech end
        sm.transition(AppState.TRANSCRIBING)
        assert sm.state == AppState.TRANSCRIBING

        # Transcription complete, no injection
        sm.transition(AppState.LISTENING)
        assert sm.state == AppState.LISTENING

    def test_injection_workflow(self) -> None:
        """Test: LISTENING → RECORDING → TRANSCRIBING → INJECTING → LISTENING."""
        sm = StateManager(initial_state=AppState.LISTENING)

        sm.transition(AppState.RECORDING)
        sm.transition(AppState.TRANSCRIBING)
        sm.transition(AppState.INJECTING)
        assert sm.state == AppState.INJECTING

        sm.transition(AppState.LISTENING)
        assert sm.state == AppState.LISTENING

    def test_short_audio_workflow(self) -> None:
        """Test: LISTENING → RECORDING → LISTENING (audio too short)."""
        sm = StateManager(initial_state=AppState.LISTENING)

        sm.transition(AppState.RECORDING)
        # Audio too short, discard
        sm.transition(AppState.LISTENING)
        assert sm.state == AppState.LISTENING

    def test_queued_audio_workflow(self) -> None:
        """Test: LISTENING → TRANSCRIBING → LISTENING (processing queued audio)."""
        sm = StateManager(initial_state=AppState.LISTENING)

        # Process queued audio directly (no recording)
        sm.transition(AppState.TRANSCRIBING)
        sm.transition(AppState.LISTENING)
        assert sm.state == AppState.LISTENING

@pytest.mark.slow
class TestThreadSafety:
    """Test thread safety of state machine."""

    def test_concurrent_reads_are_safe(self) -> None:
        """Multiple threads can read state concurrently."""
        sm = StateManager()
        results = []

        def read_state():
            for _ in range(100):
                results.append(sm.state)
                time.sleep(0.001)

        threads = [threading.Thread(target=read_state) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should return valid states
        assert len(results) == 1000
        assert all(isinstance(s, AppState) for s in results)

    def test_concurrent_transitions_state_consistency(self) -> None:
        """Concurrent transitions maintain state consistency."""
        sm = StateManager(initial_state=AppState.LISTENING)
        actual_transitions = [0]
        lock = threading.Lock()

        def try_transition_sequence():
            # Each thread tries: LISTENING → RECORDING → TRANSCRIBING
            # Only valid sequences should succeed
            if sm.try_transition(AppState.RECORDING):
                with lock:
                    actual_transitions[0] += 1
                # Try next step
                sm.try_transition(AppState.TRANSCRIBING)

        threads = [threading.Thread(target=try_transition_sequence) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # At least one transition should have occurred
        assert actual_transitions[0] >= 1
        # State should be valid (either RECORDING or TRANSCRIBING depending on timing)
        assert sm.state in (AppState.LISTENING, AppState.RECORDING, AppState.TRANSCRIBING)

    def test_concurrent_workflow_no_corruption(self) -> None:
        """State is never corrupted under concurrent access."""
        sm = StateManager(initial_state=AppState.LISTENING)
        errors = []

        def run_workflow():
            try:
                for _ in range(20):
                    # Try full workflow
                    if sm.try_transition(AppState.RECORDING):
                        if sm.try_transition(AppState.TRANSCRIBING):
                            sm.try_transition(AppState.LISTENING)
                        else:
                            sm.reset_to_listening()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=run_workflow) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions should occur
        assert len(errors) == 0
        # State should be valid
        assert sm.state in AppState

    def test_rapid_reset_is_safe(self) -> None:
        """Rapid resets from multiple threads don't corrupt state."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)

        def reset_repeatedly():
            for _ in range(100):
                sm.reset_to_listening()

        threads = [threading.Thread(target=reset_repeatedly) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sm.state == AppState.LISTENING

    def test_callback_called_outside_lock(self) -> None:
        """Callback is called outside the lock (no deadlock potential)."""
        callback_lock_held = []

        def callback(from_state, to_state):
            # If we can acquire the lock here, it means
            # the callback is called OUTSIDE the state lock
            acquired = sm._lock.acquire(blocking=False)
            callback_lock_held.append(acquired)
            if acquired:
                sm._lock.release()

        sm = StateManager(initial_state=AppState.LISTENING, on_transition=callback)
        sm.transition(AppState.RECORDING)

        # Callback should have been able to acquire lock
        assert callback_lock_held == [True]
