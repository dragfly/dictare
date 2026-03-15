"""Tests for services/tts_service.py — TTSService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dictare.services.tts_service import TTSService


def _make_config():
    config = MagicMock()
    config.tts.engine = "espeak"
    config.tts.language = "en"
    config.tts.voice = "default"
    config.tts.speed = 175
    return config


class TestTTSServiceProperties:
    def test_name(self) -> None:
        svc = TTSService(config=_make_config())
        assert svc.name == "tts"

    def test_is_available(self) -> None:
        svc = TTSService(config=_make_config())
        assert svc.is_available() is True

    def test_list_engines(self) -> None:
        svc = TTSService(config=_make_config())
        engines = svc.list_engines()
        assert "espeak" in engines
        assert "say" in engines
        assert "piper" in engines


class TestTTSServiceSpeak:
    @patch("dictare.tts.get_cached_tts_engine")
    @patch("dictare.config.TTSConfig")
    def test_speak_returns_engine_result(self, mock_tts_config, mock_get_engine) -> None:
        config = _make_config()
        svc = TTSService(config=config)

        mock_engine = MagicMock()
        mock_engine.speak.return_value = True
        mock_get_engine.return_value = mock_engine

        result = svc.speak("hello")
        assert result is True
        mock_engine.speak.assert_called_once_with("hello")

    @patch("dictare.tts.get_cached_tts_engine")
    @patch("dictare.config.TTSConfig")
    def test_speak_uses_overrides(self, mock_tts_config, mock_get_engine) -> None:
        config = _make_config()
        svc = TTSService(config=config)

        mock_engine = MagicMock()
        mock_engine.speak.return_value = True
        mock_get_engine.return_value = mock_engine

        svc.speak("hi", engine="say", language="it", voice="custom", speed=200)
        mock_tts_config.assert_called_once_with(
            engine="say", language="it", voice="custom", speed=200,
        )


class TestTTSServiceGetEngine:
    @patch("dictare.tts.get_cached_tts_engine")
    @patch("dictare.config.TTSConfig")
    def test_get_engine_returns_cached_engine(self, mock_tts_config, mock_get_engine) -> None:
        config = _make_config()
        svc = TTSService(config=config)

        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine

        engine = svc.get_engine()
        assert engine is mock_engine


class TestTTSServiceSpeakWithConfig:
    @patch("dictare.tts.get_cached_tts_engine")
    @patch("dictare.config.TTSConfig")
    def test_speak_with_config_delegates(self, mock_tts_config, mock_get_engine) -> None:
        config = _make_config()
        svc = TTSService(config=config)

        tts_cfg = MagicMock()
        tts_cfg.engine = "piper"
        tts_cfg.language = "de"
        tts_cfg.voice = "v1"
        tts_cfg.speed = 150

        mock_engine = MagicMock()
        mock_engine.speak.return_value = True
        mock_get_engine.return_value = mock_engine

        result = svc.speak_with_config("test text", tts_cfg)
        assert result is True
        mock_engine.speak.assert_called_once_with("test text")
