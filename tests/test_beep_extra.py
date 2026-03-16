"""Tests for audio feedback — sound config, play_audio, looping, speak_mode."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from dictare.audio.beep import (
    DEFAULT_SOUND_READY,
    DEFAULT_SOUND_START,
    DEFAULT_SOUND_STOP,
    DEFAULT_SOUND_SUBMIT,
    DEFAULT_SOUND_TRANSCRIBED,
    DEFAULT_SOUND_TRANSCRIBING,
    _pick_pencil_write,
    get_sound_for_event,
    get_sound_path,
    get_volume_for_event,
    is_looping,
    play_audio,
    set_output_device,
    speak_mode,
    stop_loop,
    warmup_audio,
)

# ---------------------------------------------------------------------------
# Default sound files
# ---------------------------------------------------------------------------

class TestDefaultSounds:
    """Test that bundled sound files are correct paths."""

    def test_start_sound(self) -> None:
        assert DEFAULT_SOUND_START.name == "up-beep.wav"

    def test_stop_sound(self) -> None:
        assert DEFAULT_SOUND_STOP.name == "down-beep.wav"

    def test_transcribing_sound(self) -> None:
        assert DEFAULT_SOUND_TRANSCRIBING.name == "typewriter.wav"

    def test_submit_sound(self) -> None:
        assert DEFAULT_SOUND_SUBMIT.name == "typewriter-burst.wav"

    def test_ready_sound(self) -> None:
        assert DEFAULT_SOUND_READY.name == "carriage-return.wav"

    def test_transcribed_sound(self) -> None:
        assert DEFAULT_SOUND_TRANSCRIBED.name == "pencil-write.wav"


# ---------------------------------------------------------------------------
# get_sound_path
# ---------------------------------------------------------------------------

class TestGetSoundPath:
    """Test get_sound_path helper."""

    def test_returns_path(self) -> None:
        p = get_sound_path("up-beep.wav")
        assert isinstance(p, Path)
        assert p.name == "up-beep.wav"


# ---------------------------------------------------------------------------
# set_output_device
# ---------------------------------------------------------------------------

class TestSetOutputDevice:
    """Test set_output_device."""

    def test_set_device(self) -> None:
        set_output_device("TestDevice")
        # Reset to default for other tests
        set_output_device(None)

    def test_empty_string_sets_none(self) -> None:
        set_output_device("")
        # No assertion needed, just shouldn't crash


# ---------------------------------------------------------------------------
# get_sound_for_event
# ---------------------------------------------------------------------------

class TestGetSoundForEvent:
    """Test get_sound_for_event logic."""

    def test_audio_feedback_disabled(self) -> None:
        config = MagicMock()
        config.audio_feedback = False
        enabled, path = get_sound_for_event(config, "start")
        assert enabled is False
        assert path == ""

    def test_unknown_event_with_default(self) -> None:
        config = MagicMock()
        config.audio_feedback = True
        config.sounds = {}  # no per-event config
        enabled, path = get_sound_for_event(config, "start")
        assert enabled is True
        assert "up-beep" in path

    def test_unknown_event_no_default(self) -> None:
        config = MagicMock()
        config.audio_feedback = True
        config.sounds = {}
        enabled, path = get_sound_for_event(config, "nonexistent_event")
        assert enabled is False

    def test_event_disabled(self) -> None:
        config = MagicMock()
        config.audio_feedback = True
        sound_cfg = MagicMock()
        sound_cfg.enabled = False
        config.sounds = {"start": sound_cfg}
        enabled, path = get_sound_for_event(config, "start")
        assert enabled is False

    def test_agent_announce_returns_empty_path(self) -> None:
        config = MagicMock()
        config.audio_feedback = True
        sound_cfg = MagicMock()
        sound_cfg.enabled = True
        config.sounds = {"agent_announce": sound_cfg}
        enabled, path = get_sound_for_event(config, "agent_announce")
        assert enabled is True
        assert path == ""  # TTS, not file

    def test_custom_path(self) -> None:
        config = MagicMock()
        config.audio_feedback = True
        sound_cfg = MagicMock()
        sound_cfg.enabled = True
        sound_cfg.path = "/custom/sound.wav"
        config.sounds = {"start": sound_cfg}
        enabled, path = get_sound_for_event(config, "start")
        assert enabled is True
        assert path == "/custom/sound.wav"

    def test_transcribed_uses_random_clip(self) -> None:
        config = MagicMock()
        config.audio_feedback = True
        sound_cfg = MagicMock()
        sound_cfg.enabled = True
        sound_cfg.path = None
        config.sounds = {"transcribed": sound_cfg}
        enabled, path = get_sound_for_event(config, "transcribed")
        assert enabled is True
        assert "pencil-write" in path


# ---------------------------------------------------------------------------
# get_volume_for_event
# ---------------------------------------------------------------------------

class TestGetVolumeForEvent:
    """Test get_volume_for_event."""

    def test_no_config_returns_1(self) -> None:
        config = MagicMock()
        config.sounds = {}
        vol = get_volume_for_event(config, "start")
        assert vol == 1.0

    def test_returns_configured_volume(self) -> None:
        config = MagicMock()
        sound_cfg = MagicMock()
        sound_cfg.volume = 0.5
        config.sounds = {"start": sound_cfg}
        vol = get_volume_for_event(config, "start")
        assert vol == 0.5


# ---------------------------------------------------------------------------
# _pick_pencil_write
# ---------------------------------------------------------------------------

class TestPickPencilWrite:
    """Test random pencil-write clip selection."""

    def test_returns_path(self) -> None:
        p = _pick_pencil_write()
        assert isinstance(p, Path)
        assert "pencil-write" in p.name


# ---------------------------------------------------------------------------
# warmup_audio
# ---------------------------------------------------------------------------

class TestWarmupAudio:
    """Test warmup_audio no-op."""

    def test_noop(self) -> None:
        warmup_audio()  # should not raise


# ---------------------------------------------------------------------------
# play_audio — callable source
# ---------------------------------------------------------------------------

class TestPlayAudioCallable:
    """Test play_audio with callable source (TTS)."""

    def test_callable_no_pause(self) -> None:
        """Callable source without pause runs in background thread."""
        called = threading.Event()
        fn = lambda: called.set()  # noqa: E731
        play_audio(fn, pause_mic=False)
        called.wait(timeout=2)
        assert called.is_set()

    def test_callable_pause_no_controller(self) -> None:
        """Callable with pause but no controller — runs without pausing."""
        called = threading.Event()
        fn = lambda: called.set()  # noqa: E731
        play_audio(fn, pause_mic=True, controller=None)
        called.wait(timeout=2)
        assert called.is_set()

    def test_callable_pause_off_state(self) -> None:
        """Callable with pause + controller in OFF state — no state transition."""
        from dictare.core.fsm import AppState

        controller = MagicMock()
        controller.state = AppState.OFF

        called = threading.Event()
        fn = lambda: called.set()  # noqa: E731
        play_audio(fn, pause_mic=True, controller=controller)
        called.wait(timeout=2)
        assert called.is_set()
        controller.send.assert_not_called()

    def test_callable_pause_listening_sends_events(self) -> None:
        """Callable with pause + LISTENING state sends PlayStarted/PlayCompleted."""
        from dictare.core.fsm import AppState

        controller = MagicMock()
        controller.state = AppState.LISTENING

        done = threading.Event()
        fn = lambda: done.set()  # noqa: E731
        play_audio(fn, pause_mic=True, controller=controller)
        done.wait(timeout=2)
        # PlayStarted should have been sent before the thread
        assert controller.send.call_count >= 1


# ---------------------------------------------------------------------------
# play_audio — file source
# ---------------------------------------------------------------------------

class TestPlayAudioFile:
    """Test play_audio with file source."""

    def test_file_no_pause(self) -> None:
        """File source without pause enqueues to worker."""
        with patch("dictare.audio.beep.play_sound_file") as mock:
            play_audio("/fake/path.wav", pause_mic=False)
        mock.assert_called_once()

    def test_file_pause_no_controller(self) -> None:
        with patch("dictare.audio.beep.play_sound_file") as mock:
            play_audio("/fake/path.wav", pause_mic=True, controller=None)
        mock.assert_called_once()

    def test_file_pause_off_state(self) -> None:
        from dictare.core.fsm import AppState

        controller = MagicMock()
        controller.state = AppState.OFF

        with patch("dictare.audio.beep.play_sound_file") as mock:
            play_audio("/fake/path.wav", pause_mic=True, controller=controller)
        mock.assert_called_once()
        controller.send.assert_not_called()


# ---------------------------------------------------------------------------
# Loop control
# ---------------------------------------------------------------------------

class TestLoopControl:
    """Test start_loop / stop_loop / is_looping."""

    def test_initially_not_looping(self) -> None:
        stop_loop()
        assert is_looping() is False

    def test_stop_loop_when_not_looping(self) -> None:
        stop_loop()  # should not raise


# ---------------------------------------------------------------------------
# speak_mode
# ---------------------------------------------------------------------------

class TestSpeakMode:
    """Test speak_mode function."""

    def test_speak_mode_en(self) -> None:
        with patch("subprocess.run"):
            speak_mode("transcription", "en")
            # Runs in background thread, give it a moment
            import time
            time.sleep(0.05)
        # Function runs in thread, may or may not have been called yet

    def test_speak_mode_unknown_language(self) -> None:
        with patch("subprocess.run"):
            speak_mode("command", "xx")  # should not crash
