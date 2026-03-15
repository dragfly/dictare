"""Tests for services/base.py — BaseService and ServiceRegistry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dictare.services.base import BaseService, ServiceRegistry


class ConcreteService(BaseService):
    """Concrete implementation for testing the abstract base."""

    @property
    def name(self) -> str:
        return "test-service"

    def is_available(self) -> bool:
        return True


class TestBaseService:
    def test_config_stored_when_provided(self) -> None:
        config = MagicMock()
        svc = ConcreteService(config=config)
        assert svc.config is config

    def test_config_lazy_loads_when_none(self) -> None:
        svc = ConcreteService(config=None)
        with patch("dictare.config.load_config") as mock_load:
            mock_load.return_value = MagicMock()
            cfg = svc.config
            mock_load.assert_called_once()
            assert cfg is mock_load.return_value

    def test_config_lazy_loads_only_once(self) -> None:
        svc = ConcreteService(config=None)
        with patch("dictare.config.load_config") as mock_load:
            mock_load.return_value = MagicMock()
            cfg1 = svc.config
            cfg2 = svc.config
            mock_load.assert_called_once()
            assert cfg1 is cfg2

    def test_name_property(self) -> None:
        svc = ConcreteService()
        assert svc.name == "test-service"

    def test_is_available(self) -> None:
        svc = ConcreteService()
        assert svc.is_available() is True


class TestServiceRegistry:
    def test_config_lazy_loads(self) -> None:
        reg = ServiceRegistry(config=None)
        with patch("dictare.config.load_config") as mock_load:
            mock_load.return_value = MagicMock()
            cfg = reg.config
            mock_load.assert_called_once()
            assert cfg is mock_load.return_value

    def test_config_uses_provided(self) -> None:
        config = MagicMock()
        reg = ServiceRegistry(config=config)
        assert reg.config is config

    def test_stt_lazy_created(self) -> None:
        config = MagicMock()
        reg = ServiceRegistry(config=config)
        with patch("dictare.services.stt_service.STTService") as mock_cls:
            mock_cls.return_value = MagicMock()
            stt = reg.stt
            mock_cls.assert_called_once_with(config)
            assert stt is mock_cls.return_value

    def test_stt_cached(self) -> None:
        config = MagicMock()
        reg = ServiceRegistry(config=config)
        with patch("dictare.services.stt_service.STTService") as mock_cls:
            mock_cls.return_value = MagicMock()
            stt1 = reg.stt
            stt2 = reg.stt
            mock_cls.assert_called_once()
            assert stt1 is stt2

    def test_tts_lazy_created(self) -> None:
        config = MagicMock()
        reg = ServiceRegistry(config=config)
        with patch("dictare.services.tts_service.TTSService") as mock_cls:
            mock_cls.return_value = MagicMock()
            tts = reg.tts
            mock_cls.assert_called_once_with(config)
            assert tts is mock_cls.return_value
