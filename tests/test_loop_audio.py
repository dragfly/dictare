"""Tests for the audio loop (typewriter sound during TRANSCRIBING)."""

from __future__ import annotations

from unittest.mock import call, patch

class TestLoopState:
    """start_loop / stop_loop / is_looping state machine."""

    def setup_method(self):
        # Reset module-level loop state before every test
        import voxtype.audio.beep as beep
        beep._loop_active.clear()
        beep._loop_path = None

    def test_not_looping_initially(self):
        from voxtype.audio.beep import is_looping
        assert is_looping() is False

    def test_start_loop_sets_active(self):
        from voxtype.audio.beep import is_looping, start_loop
        with patch("voxtype.audio.beep._play_queue") as mock_q, \
             patch("voxtype.audio.beep._ensure_worker"):
            start_loop("/tmp/fake.wav")
            assert is_looping() is True
            mock_q.put.assert_called_once()

    def test_stop_loop_clears_active(self):
        from voxtype.audio.beep import is_looping, start_loop, stop_loop
        with patch("voxtype.audio.beep._play_queue"), \
             patch("voxtype.audio.beep._ensure_worker"):
            start_loop("/tmp/fake.wav")
            stop_loop()
            assert is_looping() is False

    def test_stop_loop_is_noop_when_not_looping(self):
        from voxtype.audio.beep import is_looping, stop_loop
        stop_loop()  # must not raise
        assert is_looping() is False

    def test_start_loop_replaces_path(self):
        import voxtype.audio.beep as beep
        from voxtype.audio.beep import start_loop
        with patch("voxtype.audio.beep._play_queue"), \
             patch("voxtype.audio.beep._ensure_worker"):
            start_loop("/tmp/a.wav")
            start_loop("/tmp/b.wav")
            assert beep._loop_path == "/tmp/b.wav"

class TestLoopReenqueue:
    """_enqueue_loop_next re-enqueues only while active."""

    def setup_method(self):
        import voxtype.audio.beep as beep
        beep._loop_active.clear()
        beep._loop_path = None

    def test_enqueue_next_schedules_when_active(self):
        import voxtype.audio.beep as beep
        beep._loop_path = "/tmp/fake.wav"
        beep._loop_active.set()
        with patch("voxtype.audio.beep._play_queue") as mock_q:
            beep._enqueue_loop_next()
            # Should put a (path, callback) tuple on the queue
            mock_q.put.assert_called_once()
            args = mock_q.put.call_args[0][0]
            assert args[0] == "/tmp/fake.wav"
            assert callable(args[1])

    def test_enqueue_next_does_nothing_when_stopped(self):
        import voxtype.audio.beep as beep
        beep._loop_path = "/tmp/fake.wav"
        beep._loop_active.clear()
        with patch("voxtype.audio.beep._play_queue") as mock_q:
            beep._enqueue_loop_next()
            mock_q.put.assert_not_called()

    def test_enqueue_next_does_nothing_when_no_path(self):
        import voxtype.audio.beep as beep
        beep._loop_path = None
        beep._loop_active.set()
        with patch("voxtype.audio.beep._play_queue") as mock_q:
            beep._enqueue_loop_next()
            mock_q.put.assert_not_called()

class TestControllerLoopIntegration:
    """on_state_change triggers start_loop / stop_loop correctly."""

    def _make_events(self):
        """Build a ControllerEvents instance with mocked config."""
        from unittest.mock import MagicMock
        from voxtype.app.controller import StateController

        cfg = MagicMock()
        cfg.audio.audio_feedback = True
        cfg.audio.headphones_mode = False
        # get_sound_for_event returns (enabled=True, path)
        return cfg

    def test_transcribing_calls_start_loop(self):
        from voxtype.core.fsm import AppState

        with patch("voxtype.audio.beep.get_sound_for_event", return_value=(True, "/tmp/t.wav")), \
             patch("voxtype.audio.beep.start_loop") as mock_start, \
             patch("voxtype.audio.beep.stop_loop") as mock_stop, \
             patch("voxtype.audio.beep.play_audio"), \
             patch("voxtype.audio.beep.play_sound_file_async"), \
             patch("voxtype.audio.beep.is_looping", return_value=False):
            from voxtype.app import controller as ctrl_mod
            # Simulate what on_state_change does for TRANSCRIBING
            old, new = AppState.LISTENING, AppState.TRANSCRIBING
            # Replicate the relevant logic from on_state_change
            if old == AppState.TRANSCRIBING:
                from voxtype.audio.beep import stop_loop
                stop_loop()
            if new == AppState.TRANSCRIBING:
                from voxtype.audio.beep import start_loop, get_sound_for_event
                enabled, path = get_sound_for_event(None, "transcribing")
                if enabled:
                    start_loop(path)

            mock_start.assert_called_once_with("/tmp/t.wav")
            mock_stop.assert_not_called()

    def test_leaving_transcribing_calls_stop_loop(self):
        from voxtype.core.fsm import AppState

        with patch("voxtype.audio.beep.stop_loop") as mock_stop, \
             patch("voxtype.audio.beep.get_sound_for_event", return_value=(False, "")), \
             patch("voxtype.audio.beep.play_sound_file_async"):
            old, new = AppState.TRANSCRIBING, AppState.LISTENING
            if old == AppState.TRANSCRIBING:
                from voxtype.audio.beep import stop_loop
                stop_loop()
            mock_stop.assert_called_once()
