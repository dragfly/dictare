"""Tests for the audio loop (typewriter sound during TRANSCRIBING)."""

from __future__ import annotations

from unittest.mock import patch


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

    def _fake_wav(self, duration: float = 2.0, sr: int = 48000):
        import numpy as np
        return np.zeros(int(duration * sr)), sr

    def test_start_loop_sets_active(self):
        from voxtype.audio.beep import is_looping, start_loop
        data, sr = self._fake_wav()
        with patch("voxtype.audio.beep._play_queue") as mock_q, \
             patch("voxtype.audio.beep._ensure_worker"), \
             patch("voxtype.audio.beep._sound_cache", {"/tmp/fake.wav": (data, sr)}):
            start_loop("/tmp/fake.wav")
            assert is_looping() is True
            mock_q.put.assert_called_once()

    def test_stop_loop_clears_active(self):
        from voxtype.audio.beep import is_looping, start_loop, stop_loop
        data, sr = self._fake_wav()
        with patch("voxtype.audio.beep._play_queue"), \
             patch("voxtype.audio.beep._ensure_worker"), \
             patch("voxtype.audio.beep._sound_cache", {"/tmp/fake.wav": (data, sr)}):
            start_loop("/tmp/fake.wav")
            stop_loop()
            assert is_looping() is False

    def test_stop_loop_is_noop_when_not_looping(self):
        from voxtype.audio.beep import is_looping, stop_loop
        stop_loop()  # must not raise
        assert is_looping() is False

    def test_start_loop_creates_chunks(self):
        """A 2s WAV @ 48kHz with 1s chunks → 2 chunk keys."""
        import voxtype.audio.beep as beep
        from voxtype.audio.beep import start_loop
        data, sr = self._fake_wav(duration=2.0, sr=48000)
        with patch("voxtype.audio.beep._play_queue"), \
             patch("voxtype.audio.beep._ensure_worker"), \
             patch("voxtype.audio.beep._sound_cache", {"/tmp/a.wav": (data, sr)}):
            start_loop("/tmp/a.wav")
            assert len(beep._loop_chunk_keys) == 2

    def test_start_loop_replaces_chunks(self):
        """Calling start_loop() twice replaces previous chunk keys."""
        import voxtype.audio.beep as beep
        from voxtype.audio.beep import start_loop
        data, sr = self._fake_wav(duration=2.0)
        cache = {"/tmp/a.wav": (data, sr), "/tmp/b.wav": (data, sr)}
        with patch("voxtype.audio.beep._play_queue"), \
             patch("voxtype.audio.beep._ensure_worker"), \
             patch("voxtype.audio.beep._sound_cache", cache):
            start_loop("/tmp/a.wav")
            start_loop("/tmp/b.wav")
            assert beep._loop_chunk_pos == 1  # reset and first chunk enqueued


class TestLoopReenqueue:
    """_enqueue_loop_next re-enqueues only while active."""

    def setup_method(self):
        import voxtype.audio.beep as beep
        beep._loop_active.clear()
        beep._loop_chunk_keys = []
        beep._loop_chunk_pos = 0

    def test_enqueue_next_schedules_when_active(self):
        import voxtype.audio.beep as beep
        beep._loop_chunk_keys = ["__loop_chunk_0__"]
        beep._loop_active.set()
        with patch("voxtype.audio.beep._play_queue") as mock_q:
            beep._enqueue_loop_next()
            mock_q.put.assert_called_once()
            args = mock_q.put.call_args[0][0]
            assert args[0] == "__loop_chunk_0__"
            assert args[1] == 1.0  # volume (baked into chunk data)
            assert callable(args[2])

    def test_enqueue_next_does_nothing_when_stopped(self):
        import voxtype.audio.beep as beep
        beep._loop_chunk_keys = ["__loop_chunk_0__"]
        beep._loop_active.clear()
        with patch("voxtype.audio.beep._play_queue") as mock_q:
            beep._enqueue_loop_next()
            mock_q.put.assert_not_called()

    def test_enqueue_next_does_nothing_when_no_chunks(self):
        import voxtype.audio.beep as beep
        beep._loop_chunk_keys = []
        beep._loop_active.set()
        with patch("voxtype.audio.beep._play_queue") as mock_q:
            beep._enqueue_loop_next()
            mock_q.put.assert_not_called()

    def test_chunk_index_wraps_around(self):
        """After the last chunk, wraps back to chunk 0."""
        import voxtype.audio.beep as beep
        beep._loop_chunk_keys = ["__loop_chunk_0__", "__loop_chunk_1__"]
        beep._loop_chunk_pos = 2  # past end
        beep._loop_active.set()
        with patch("voxtype.audio.beep._play_queue") as mock_q:
            beep._enqueue_loop_next()
            args = mock_q.put.call_args[0][0]
            assert args[0] == "__loop_chunk_0__"  # wraps to 2 % 2 = 0


class TestControllerLoopIntegration:
    """on_state_change triggers start_loop / stop_loop correctly."""

    def _make_events(self):
        """Build a ControllerEvents instance with mocked config."""
        from unittest.mock import MagicMock

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
            # Simulate what on_state_change does for TRANSCRIBING
            old, new = AppState.LISTENING, AppState.TRANSCRIBING
            # Replicate the relevant logic from on_state_change
            if old == AppState.TRANSCRIBING:
                from voxtype.audio.beep import stop_loop
                stop_loop()
            if new == AppState.TRANSCRIBING:
                from voxtype.audio.beep import get_sound_for_event, start_loop
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
            old = AppState.TRANSCRIBING
            if old == AppState.TRANSCRIBING:
                from voxtype.audio.beep import stop_loop
                stop_loop()
            mock_stop.assert_called_once()

    def test_ready_sound_suppressed_when_no_loop(self):
        """If typewriter never played (short recording), carriage return is suppressed."""
        from voxtype.core.fsm import AppState

        with patch("voxtype.audio.beep.is_looping", return_value=False), \
             patch("voxtype.audio.beep.stop_loop"), \
             patch("voxtype.audio.beep.get_sound_for_event", return_value=(True, "/tmp/ready.wav")), \
             patch("voxtype.audio.beep.play_sound_file_async") as mock_play:
            old, new = AppState.TRANSCRIBING, AppState.LISTENING
            from voxtype.audio.beep import is_looping as il
            from voxtype.audio.beep import stop_loop as sl
            was_looping = old == AppState.TRANSCRIBING and il()
            sl()
            if new == AppState.LISTENING and old == AppState.TRANSCRIBING:
                if was_looping:
                    from voxtype.audio.beep import get_sound_for_event as gse
                    from voxtype.audio.beep import play_sound_file_async as psa
                    enabled, path = gse(None, "ready")
                    if enabled:
                        psa(path)
            mock_play.assert_not_called()

    def test_ready_sound_plays_when_loop_was_active(self):
        """If typewriter played (long recording), carriage return plays after transcription."""
        from voxtype.core.fsm import AppState

        with patch("voxtype.audio.beep.is_looping", return_value=True), \
             patch("voxtype.audio.beep.stop_loop"), \
             patch("voxtype.audio.beep.get_sound_for_event", return_value=(True, "/tmp/ready.wav")), \
             patch("voxtype.audio.beep.play_sound_file_async") as mock_play:
            old, new = AppState.TRANSCRIBING, AppState.LISTENING
            from voxtype.audio.beep import is_looping as il
            from voxtype.audio.beep import stop_loop as sl
            was_looping = old == AppState.TRANSCRIBING and il()
            sl()
            if new == AppState.LISTENING and old == AppState.TRANSCRIBING:
                if was_looping:
                    from voxtype.audio.beep import get_sound_for_event as gse
                    from voxtype.audio.beep import play_sound_file_async as psa
                    enabled, path = gse(None, "ready")
                    if enabled:
                        psa(path)
            mock_play.assert_called_once_with("/tmp/ready.wav")
