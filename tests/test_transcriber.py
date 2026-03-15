"""Tests for core/transcriber.py — OneShotTranscriber."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from dictare.core.transcriber import OneShotTranscriber


def _make_config():
    """Create a minimal mock config."""
    config = MagicMock()
    config.audio.advanced.sample_rate = 16000
    config.audio.advanced.channels = 1
    config.audio.advanced.device = None
    config.stt.language = "en"
    config.stt.advanced.beam_size = 5
    config.stt.advanced.max_repetitions = 5
    return config


def _make_stt_engine(text: str = "hello world"):
    """Create a mock STT engine that returns the given text."""
    engine = MagicMock()
    result = MagicMock()
    result.text = text
    engine.transcribe.return_value = result
    return engine


class TestOneShotTranscriberInit:
    def test_defaults(self) -> None:
        config = _make_config()
        engine = _make_stt_engine()
        t = OneShotTranscriber(config, engine)
        assert t.silence_ms == 1200
        assert t.max_duration == 60
        assert t.quiet is False

    def test_custom_params(self) -> None:
        config = _make_config()
        engine = _make_stt_engine()
        t = OneShotTranscriber(config, engine, silence_ms=500, max_duration=10, quiet=True)
        assert t.silence_ms == 500
        assert t.max_duration == 10
        assert t.quiet is True


class TestOneShotTranscriberCallbacks:
    def test_on_speech_start_sets_flag(self) -> None:
        config = _make_config()
        engine = _make_stt_engine()
        t = OneShotTranscriber(config, engine, quiet=True)
        assert t._speech_started is False
        t._on_speech_start()
        assert t._speech_started is True

    def test_on_speech_end_stores_audio_and_signals_done(self) -> None:
        config = _make_config()
        engine = _make_stt_engine()
        t = OneShotTranscriber(config, engine)
        audio = np.zeros(1600, dtype=np.float32)
        t._on_speech_end(audio)
        assert t._audio_data is not None
        assert len(t._audio_data) == 1600
        assert t._done.is_set()


class TestOneShotTranscriberSignal:
    def test_signal_handler_cancels(self) -> None:
        config = _make_config()
        engine = _make_stt_engine()
        t = OneShotTranscriber(config, engine)
        t._audio_capture = MagicMock()
        t._signal_handler(2, None)
        assert t._cancelled.is_set()
        assert t._done.is_set()
        t._audio_capture.stop_streaming.assert_called_once()


class TestOneShotTranscriberRecordAndTranscribe:
    @patch("dictare.core.transcriber.AudioCapture")
    @patch("dictare.core.transcriber.SileroVAD")
    @patch("dictare.core.transcriber.StreamingVAD")
    def test_returns_empty_when_cancelled(self, mock_svad, mock_vad, mock_capture) -> None:
        config = _make_config()
        engine = _make_stt_engine()
        t = OneShotTranscriber(config, engine, quiet=True)

        # Simulate: start_streaming immediately triggers cancel
        def start_side_effect(callback):
            t._cancelled.set()
            t._done.set()

        mock_capture.return_value.start_streaming.side_effect = start_side_effect
        result = t.record_and_transcribe()
        assert result == ""

    @patch("dictare.core.transcriber.AudioCapture")
    @patch("dictare.core.transcriber.SileroVAD")
    @patch("dictare.core.transcriber.StreamingVAD")
    def test_returns_empty_when_no_audio(self, mock_svad, mock_vad, mock_capture) -> None:
        config = _make_config()
        engine = _make_stt_engine()
        t = OneShotTranscriber(config, engine, quiet=True)

        def start_side_effect(callback):
            t._done.set()

        mock_capture.return_value.start_streaming.side_effect = start_side_effect
        result = t.record_and_transcribe()
        assert result == ""

    @patch("dictare.core.transcriber.AudioCapture")
    @patch("dictare.core.transcriber.SileroVAD")
    @patch("dictare.core.transcriber.StreamingVAD")
    def test_transcribes_audio_when_speech_ends(self, mock_svad, mock_vad, mock_capture) -> None:
        config = _make_config()
        engine = _make_stt_engine("  hello world  ")
        t = OneShotTranscriber(config, engine, quiet=True)

        audio = np.ones(1600, dtype=np.float32)

        def start_side_effect(callback):
            # Simulate VAD detecting speech end
            t._on_speech_end(audio)

        mock_capture.return_value.start_streaming.side_effect = start_side_effect
        result = t.record_and_transcribe()
        assert result == "hello world"
        engine.transcribe.assert_called_once()
