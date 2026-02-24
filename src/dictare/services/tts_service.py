"""Text-to-speech service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dictare.services.base import BaseService

if TYPE_CHECKING:
    from dictare.config import Config, TTSConfig
    from dictare.tts.base import TTSEngine


class TTSService(BaseService):
    """Text-to-speech service.

    Provides high-level TTS API with engine caching for performance.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize TTS service.

        Args:
            config: Configuration object. If None, loads default config.
        """
        super().__init__(config)

    @property
    def name(self) -> str:
        """Get service name."""
        return "tts"

    def is_available(self) -> bool:
        """Check if TTS service is available."""
        return True

    def speak(
        self,
        text: str,
        *,
        engine: str | None = None,
        language: str | None = None,
        voice: str | None = None,
        speed: int | None = None,
    ) -> bool:
        """Speak text aloud.

        Args:
            text: Text to speak.
            engine: TTS engine override (espeak, say, piper, coqui, outetts).
            language: Language code override.
            voice: Voice name or speaker WAV path override.
            speed: Speech speed override (WPM).

        Returns:
            True if speech was successful.
        """
        from dictare.config import TTSConfig
        from dictare.tts import get_cached_tts_engine

        tts_config = TTSConfig(
            engine=engine or self.config.tts.engine,  # type: ignore[arg-type]
            language=language or self.config.tts.language,
            voice=voice or self.config.tts.voice,
            speed=speed or self.config.tts.speed,
        )

        tts_engine = get_cached_tts_engine(tts_config)
        return tts_engine.speak(text)

    def speak_with_config(
        self,
        text: str,
        tts_config: TTSConfig,
    ) -> bool:
        """Speak text using a specific TTSConfig.

        Args:
            text: Text to speak.
            tts_config: TTS configuration to use.

        Returns:
            True if speech was successful.
        """
        return self.speak(
            text,
            engine=tts_config.engine,
            language=tts_config.language,
            voice=tts_config.voice,
            speed=tts_config.speed,
        )

    def get_engine(
        self,
        engine: str | None = None,
        language: str | None = None,
        voice: str | None = None,
        speed: int | None = None,
    ) -> TTSEngine:
        """Get a local TTS engine (for direct access).

        Args:
            engine: TTS engine name override.
            language: Language code override.
            voice: Voice name override.
            speed: Speech speed override.

        Returns:
            Configured TTS engine.
        """
        from dictare.config import TTSConfig
        from dictare.tts import get_cached_tts_engine

        tts_config = TTSConfig(
            engine=engine or self.config.tts.engine,  # type: ignore[arg-type]
            language=language or self.config.tts.language,
            voice=voice or self.config.tts.voice,
            speed=speed or self.config.tts.speed,
        )

        return get_cached_tts_engine(tts_config)

    def list_engines(self) -> list[str]:
        """List available TTS engines.

        Returns:
            List of engine names.
        """
        return ["espeak", "say", "piper", "coqui", "qwen3", "outetts"]
