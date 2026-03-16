"""Tests for TTSManager — properties, speech, lifecycle, mic pausing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dictare.core.tts_manager import TTSManager


def _make_config() -> MagicMock:
    config = MagicMock()
    config.tts.engine = "espeak"
    config.tts.language = "en"
    config.tts.speed = 175
    config.tts.voice = ""
    config.audio.audio_feedback = True
    config.audio.headphones_mode = True
    config.audio.sounds = {}
    return config


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class TestTTSManagerProperties:
    """Test TTSManager properties."""

    def test_initially_unavailable(self) -> None:
        mgr = TTSManager(_make_config())
        assert mgr.available is False
        assert mgr.engine is None

    def test_error_initially_empty(self) -> None:
        mgr = TTSManager(_make_config())
        assert mgr.error == ""

    def test_auth_token_is_hex(self) -> None:
        mgr = TTSManager(_make_config())
        assert len(mgr.auth_token) == 64
        int(mgr.auth_token, 16)  # should not raise

    def test_loading_status_initially_empty(self) -> None:
        mgr = TTSManager(_make_config())
        assert mgr.loading_status == {}

    def test_engine_property(self) -> None:
        mgr = TTSManager(_make_config())
        fake_engine = MagicMock()
        mgr._tts_engine = fake_engine
        assert mgr.engine is fake_engine
        assert mgr.available is True


# ---------------------------------------------------------------------------
# handle_speech
# ---------------------------------------------------------------------------

class TestHandleSpeech:
    """Test handle_speech method."""

    def test_empty_text_returns_error(self) -> None:
        mgr = TTSManager(_make_config())
        result = mgr.handle_speech({"text": ""})
        assert result["status"] == "error"
        assert "No text" in result["error"]

    def test_no_engine_returns_error(self) -> None:
        mgr = TTSManager(_make_config())
        result = mgr.handle_speech({"text": "hello"})
        assert result["status"] == "error"

    def test_engine_error_returns_error_message(self) -> None:
        mgr = TTSManager(_make_config())
        mgr._tts_error = "Failed to load"
        result = mgr.handle_speech({"text": "hello"})
        assert result["status"] == "error"
        assert "Failed to load" in result["error"]

    def test_engine_mismatch_raises(self) -> None:
        mgr = TTSManager(_make_config())
        with pytest.raises(ValueError, match="not the configured"):
            mgr.handle_speech({"text": "hello", "engine": "kokoro"})

    def test_successful_speech(self) -> None:
        mgr = TTSManager(_make_config())
        engine = MagicMock()
        engine.speak.return_value = True
        mgr._tts_engine = engine

        result = mgr.handle_speech({"text": "hello"})
        assert result["status"] == "ok"
        assert "duration_ms" in result
        engine.speak.assert_called_once()

    def test_speech_with_voice_override(self) -> None:
        mgr = TTSManager(_make_config())
        engine = MagicMock()
        engine.speak.return_value = True
        mgr._tts_engine = engine

        mgr.handle_speech({"text": "hello", "voice": "alice"})
        engine.speak.assert_called_once_with("hello", voice="alice")

    def test_speech_failure_returns_error(self) -> None:
        mgr = TTSManager(_make_config())
        engine = MagicMock()
        engine.speak.return_value = False
        mgr._tts_engine = engine

        result = mgr.handle_speech({"text": "hello"})
        assert result["status"] == "error"

    def test_speech_pauses_mic_when_not_headphones(self) -> None:
        config = _make_config()
        config.audio.headphones_mode = False
        controller = MagicMock()
        mgr = TTSManager(config, controller=controller)
        engine = MagicMock()
        engine.speak.return_value = True
        mgr._tts_engine = engine

        # Controller state is not OFF → should send PlayStarted/PlayCompleted
        from dictare.core.fsm import AppState
        controller.state = AppState.LISTENING

        mgr.handle_speech({"text": "hello"})
        # Verify play counter was incremented and decremented
        assert mgr._active_plays == 0


# ---------------------------------------------------------------------------
# Mic pausing (play counter)
# ---------------------------------------------------------------------------

class TestMicPausing:
    """Test _play_start / _play_end thread-safe play counter."""

    def test_play_start_increments(self) -> None:
        mgr = TTSManager(_make_config())
        mgr._play_start()
        assert mgr._active_plays == 1

    def test_play_end_decrements(self) -> None:
        mgr = TTSManager(_make_config())
        mgr._active_plays = 2
        mgr._play_end()
        assert mgr._active_plays == 1

    def test_play_end_at_zero_stays_zero(self) -> None:
        mgr = TTSManager(_make_config())
        mgr._play_end()
        assert mgr._active_plays == 0

    def test_first_play_sends_play_started(self) -> None:
        from dictare.core.fsm import AppState

        controller = MagicMock()
        controller.state = AppState.LISTENING
        mgr = TTSManager(_make_config(), controller=controller)

        mgr._play_start()
        controller.send.assert_called_once()

    def test_last_play_end_sends_play_completed(self) -> None:
        controller = MagicMock()
        mgr = TTSManager(_make_config(), controller=controller)
        mgr._active_plays = 1

        mgr._play_end()
        controller.send.assert_called_once()


# ---------------------------------------------------------------------------
# speak_text
# ---------------------------------------------------------------------------

class TestSpeakText:
    """Test speak_text method."""

    def test_speak_text_with_error(self) -> None:
        mgr = TTSManager(_make_config())
        mgr._tts_error = "Failed"
        mgr.speak_text("hello")  # should not raise

    def test_speak_text_no_engine(self) -> None:
        mgr = TTSManager(_make_config())
        mgr.speak_text("hello")  # should not raise

    def test_speak_text_disabled(self) -> None:
        config = _make_config()
        config.audio.audio_feedback = False
        mgr = TTSManager(config)
        engine = MagicMock()
        mgr._tts_engine = engine
        mgr.speak_text("hello")
        # speak() should not be called since audio_feedback is False
        engine.speak.assert_not_called()


# ---------------------------------------------------------------------------
# speak_agent
# ---------------------------------------------------------------------------

class TestSpeakAgent:
    """Test speak_agent method."""

    def test_speak_agent_strips_underscores(self) -> None:
        mgr = TTSManager(_make_config())
        mgr.speak_text = MagicMock()  # type: ignore[method-assign]
        with patch.object(mgr, "_load_tts_phrases", return_value={"agent": "agent"}):
            mgr.speak_agent("__tts__")
        mgr.speak_text.assert_called_once_with("agent tts")

    def test_speak_agent_custom_prefix(self) -> None:
        mgr = TTSManager(_make_config())
        mgr.speak_text = MagicMock()  # type: ignore[method-assign]
        with patch.object(mgr, "_load_tts_phrases", return_value={"agent": "switching to"}):
            mgr.speak_agent("claude")
        mgr.speak_text.assert_called_once_with("switching to claude")


# ---------------------------------------------------------------------------
# list_voices
# ---------------------------------------------------------------------------

class TestListVoices:
    """Test list_voices method."""

    def test_no_engine_returns_empty(self) -> None:
        config = _make_config()
        config.tts.engine = "say"
        mgr = TTSManager(config)
        assert mgr.list_voices() == []

    def test_delegates_to_engine(self) -> None:
        config = _make_config()
        config.tts.engine = "say"
        mgr = TTSManager(config)
        engine = MagicMock()
        engine.list_voices.return_value = ["alice", "bob"]
        mgr._tts_engine = engine
        assert mgr.list_voices() == ["alice", "bob"]


# ---------------------------------------------------------------------------
# precache_phrases
# ---------------------------------------------------------------------------

class TestPrecachePhrases:
    """Test precache_phrases method."""

    def test_empty_phrases_noop(self) -> None:
        mgr = TTSManager(_make_config())
        mgr.precache_phrases([])  # should not raise

    def test_no_engine_noop(self) -> None:
        mgr = TTSManager(_make_config())
        mgr.precache_phrases(["hello"])  # should not raise

    def test_worker_engine_skipped(self) -> None:
        mgr = TTSManager(_make_config())
        mgr._tts_engine = MagicMock()
        mgr._tts_proxy = MagicMock()  # worker mode
        mgr.precache_phrases(["hello"])
        # No thread should be started for worker engines


# ---------------------------------------------------------------------------
# complete_tts
# ---------------------------------------------------------------------------

class TestCompleteTTS:
    """Test complete_tts method."""

    def test_no_proxy_noop(self) -> None:
        mgr = TTSManager(_make_config())
        mgr.complete_tts("abc", ok=True, duration_ms=100)  # should not raise

    def test_delegates_to_proxy(self) -> None:
        mgr = TTSManager(_make_config())
        proxy = MagicMock()
        mgr._tts_proxy = proxy
        mgr.complete_tts("abc", ok=True, duration_ms=100)
        proxy.complete.assert_called_once_with("abc", ok=True, duration_ms=100)


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

class TestTTSManagerStop:
    """Test TTSManager.stop()."""

    def test_stop_without_worker(self) -> None:
        mgr = TTSManager(_make_config())
        mgr.stop()  # should not raise

    def test_stop_terminates_worker(self) -> None:
        mgr = TTSManager(_make_config())
        proc = MagicMock()
        mgr._tts_worker_process = proc
        mgr.stop()
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once()
        assert mgr._tts_worker_process is None


# ---------------------------------------------------------------------------
# stop_speaking
# ---------------------------------------------------------------------------

class TestStopSpeaking:
    """Test stop_speaking method."""

    def test_no_worker_calls_stop_audio_native(self) -> None:
        mgr = TTSManager(_make_config())
        with patch("dictare.tts.base.stop_audio_native", return_value=True) as mock:
            result = mgr.stop_speaking()
        assert result is True
        mock.assert_called_once()

    def test_worker_sends_sigusr2(self) -> None:
        mgr = TTSManager(_make_config())
        proc = MagicMock()
        proc.pid = 12345
        mgr._tts_worker_process = proc

        with patch("os.kill") as mock_kill:
            result = mgr.stop_speaking()
        assert result is True
        mock_kill.assert_called_once()


# ---------------------------------------------------------------------------
# _load_tts_phrases
# ---------------------------------------------------------------------------

class TestLoadTTSPhrases:
    """Test _load_tts_phrases static method."""

    def test_default_phrases(self) -> None:
        phrases = TTSManager._load_tts_phrases()
        assert "agent" in phrases
        assert phrases["agent"] == "agent"

    def test_custom_phrases(self, tmp_path) -> None:
        import json

        phrases_file = tmp_path / ".config" / "dictare" / "tts_phrases.json"
        phrases_file.parent.mkdir(parents=True)
        phrases_file.write_text(json.dumps({"agent": "switching to"}))

        with patch("pathlib.Path.home", return_value=tmp_path):
            phrases = TTSManager._load_tts_phrases()
        assert phrases["agent"] == "switching to"

    def test_corrupt_json_falls_back(self, tmp_path) -> None:
        phrases_file = tmp_path / ".config" / "dictare" / "tts_phrases.json"
        phrases_file.parent.mkdir(parents=True)
        phrases_file.write_text("not json")

        with patch("pathlib.Path.home", return_value=tmp_path):
            phrases = TTSManager._load_tts_phrases()
        assert phrases["agent"] == "agent"


# ---------------------------------------------------------------------------
# _load_in_process
# ---------------------------------------------------------------------------

class TestLoadInProcess:
    """Test _load_in_process method."""

    def test_load_success(self) -> None:
        mgr = TTSManager(_make_config())
        mgr._loading_status = {"start_time": 0, "status": "loading"}

        mock_engine = MagicMock()
        mock_engine._get_model_path = MagicMock()

        with patch("dictare.tts.get_cached_tts_engine", return_value=mock_engine):
            mgr._load_in_process("espeak")

        assert mgr._tts_engine is mock_engine
        assert mgr._loading_status["status"] == "done"

    def test_load_failure(self) -> None:
        mgr = TTSManager(_make_config())
        mgr._loading_status = {"start_time": 0, "status": "loading"}

        with patch("dictare.tts.get_cached_tts_engine", side_effect=ValueError("not found")):
            mgr._load_in_process("espeak")

        assert mgr._tts_engine is None
        assert mgr._loading_status["status"] == "error"
        assert "not found" in mgr._tts_error
