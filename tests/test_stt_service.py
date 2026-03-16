"""Tests for services/stt_service.py — STTService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from dictare.services.stt_service import STTService


def _make_config():
    config = MagicMock()
    config.stt.model = "large-v3-turbo"
    config.stt.language = "en"
    config.stt.hw_accel = True
    config.stt.advanced.device = "auto"
    config.stt.advanced.compute_type = "int8"
    config.stt.advanced.beam_size = 5
    config.stt.advanced.max_repetitions = 5
    config.stt.advanced.hotwords = None
    config.log_level = "info"
    return config


class TestSTTServiceProperties:
    def test_name(self) -> None:
        svc = STTService(config=_make_config())
        assert svc.name == "stt"

    def test_is_available(self) -> None:
        svc = STTService(config=_make_config())
        assert svc.is_available() is True

    def test_is_loaded_false_initially(self) -> None:
        svc = STTService(config=_make_config())
        assert svc.is_loaded() is False

    def test_is_loaded_true_when_engine_loaded(self) -> None:
        svc = STTService(config=_make_config())
        mock_engine = MagicMock()
        mock_engine.is_loaded.return_value = True
        svc._engine = mock_engine
        assert svc.is_loaded() is True


class TestSTTServiceEnsureEngine:
    def test_caches_engine(self) -> None:
        """Once loaded, the same engine is returned for the same model size."""
        config = _make_config()
        svc = STTService(config=config)

        mock_engine = MagicMock()
        svc._engine = mock_engine
        svc._engine_model_size = "large-v3-turbo"

        result = svc._ensure_engine("large-v3-turbo")
        assert result is mock_engine

    def test_reloads_when_model_size_changes(self) -> None:
        """Engine is recreated when requesting a different model size."""
        config = _make_config()
        svc = STTService(config=config)

        mock_engine = MagicMock()
        svc._engine = mock_engine
        svc._engine_model_size = "base"

        # Requesting "small" should clear the engine
        with patch("dictare.stt.parakeet.is_parakeet_model", return_value=False), \
             patch("dictare.utils.hardware.is_mlx_available", return_value=False), \
             patch("dictare.stt.faster_whisper.FasterWhisperEngine") as mock_cls:
            new_engine = MagicMock()
            mock_cls.return_value = new_engine
            result = svc._ensure_engine("small")
            assert result is new_engine
            assert svc._engine_model_size == "small"


class TestSTTServiceTranscribe:
    def test_transcribe_returns_text(self) -> None:
        config = _make_config()
        svc = STTService(config=config)

        mock_result = MagicMock()
        mock_result.text = "hello world"
        mock_engine = MagicMock()
        mock_engine.transcribe.return_value = mock_result
        svc._engine = mock_engine
        svc._engine_model_size = "large-v3-turbo"

        audio = np.zeros(1600, dtype=np.float32)
        text = svc.transcribe(audio)
        assert text == "hello world"

    def test_translate_uses_translate_task(self) -> None:
        config = _make_config()
        svc = STTService(config=config)

        mock_result = MagicMock()
        mock_result.text = "translated"
        mock_engine = MagicMock()
        mock_engine.transcribe.return_value = mock_result
        svc._engine = mock_engine
        svc._engine_model_size = "large-v3-turbo"

        audio = np.zeros(1600, dtype=np.float32)
        text = svc.translate(audio)
        assert text == "translated"
        call_kwargs = mock_engine.transcribe.call_args[1]
        assert call_kwargs["task"] == "translate"

    def test_transcribe_uses_explicit_params_over_config(self) -> None:
        config = _make_config()
        svc = STTService(config=config)

        mock_result = MagicMock()
        mock_result.text = "test"
        mock_engine = MagicMock()
        mock_engine.transcribe.return_value = mock_result
        svc._engine = mock_engine
        svc._engine_model_size = "large-v3-turbo"

        audio = np.zeros(1600, dtype=np.float32)
        svc.transcribe(audio, language="fr", beam_size=3, max_repetitions=2, hotwords="test")
        call_kwargs = mock_engine.transcribe.call_args[1]
        assert call_kwargs["language"] == "fr"
        assert call_kwargs["beam_size"] == 3
        assert call_kwargs["max_repetitions"] == 2
        assert call_kwargs["hotwords"] == "test"

    def test_transcribe_uses_config_defaults(self) -> None:
        config = _make_config()
        config.stt.language = "it"
        config.stt.advanced.beam_size = 7
        config.stt.advanced.max_repetitions = 3
        config.stt.advanced.hotwords = "ciao,mondo"
        svc = STTService(config=config)

        mock_result = MagicMock()
        mock_result.text = "ciao"
        mock_engine = MagicMock()
        mock_engine.transcribe.return_value = mock_result
        svc._engine = mock_engine
        svc._engine_model_size = "large-v3-turbo"

        audio = np.zeros(1600, dtype=np.float32)
        svc.transcribe(audio)
        call_kwargs = mock_engine.transcribe.call_args[1]
        assert call_kwargs["language"] == "it"
        assert call_kwargs["beam_size"] == 7
        assert call_kwargs["max_repetitions"] == 3
        assert call_kwargs["hotwords"] == "ciao,mondo"
