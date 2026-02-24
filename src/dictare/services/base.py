"""Base service class and service registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictare.config import Config

class BaseService(ABC):
    """Abstract base class for dictare services.

    Services provide high-level APIs for STT, TTS, and other features.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize service.

        Args:
            config: Configuration object. If None, loads default config.
        """
        self._config = config

    @property
    def config(self) -> Config:
        """Get configuration, loading lazily if needed."""
        if self._config is None:
            from dictare.config import load_config

            self._config = load_config()
        return self._config

    @abstractmethod
    def is_available(self) -> bool:
        """Check if service is available.

        Returns:
            True if service can be used.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Get service name."""
        pass

class ServiceRegistry:
    """Registry for dictare services.

    Provides lazy-loaded access to services.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize registry.

        Args:
            config: Configuration object. If None, loads default config.
        """
        self._config = config
        self._stt: STTService | None = None
        self._tts: TTSService | None = None

    @property
    def config(self) -> Config:
        """Get configuration, loading lazily if needed."""
        if self._config is None:
            from dictare.config import load_config

            self._config = load_config()
        return self._config

    @property
    def stt(self) -> STTService:
        """Get STT service (lazy loaded)."""
        if self._stt is None:
            from dictare.services.stt_service import STTService

            self._stt = STTService(self._config)
        return self._stt

    @property
    def tts(self) -> TTSService:
        """Get TTS service (lazy loaded)."""
        if self._tts is None:
            from dictare.services.tts_service import TTSService

            self._tts = TTSService(self._config)
        return self._tts

# Type hints for lazy imports
if TYPE_CHECKING:
    from dictare.services.stt_service import STTService
    from dictare.services.tts_service import TTSService
