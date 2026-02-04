"""Text-to-speech service with daemon integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from voxtype.services.base import BaseService

if TYPE_CHECKING:
    from voxtype.config import Config, TTSConfig
    from voxtype.tts.base import TTSEngine

class TTSService(BaseService):
    """Text-to-speech service.

    Provides high-level TTS API with:
    - Automatic daemon integration when available
    - Fallback to local engine when daemon is not running
    - Engine caching for performance
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
        """Check if TTS service is available.

        Returns:
            True if daemon is running or local engine can be created.
        """
        return self._daemon_available() or self._can_create_local()

    def _daemon_available(self) -> bool:
        """Check if daemon is running."""
        try:
            from voxtype.daemon.client import is_daemon_running

            return is_daemon_running()
        except Exception:
            return False

    def _can_create_local(self) -> bool:
        """Check if local TTS engine can be created."""
        try:
            from voxtype.tts import create_tts_engine

            engine = create_tts_engine(self.config.tts)
            return engine.is_available()
        except Exception:
            return False

    def speak(
        self,
        text: str,
        *,
        engine: str | None = None,
        language: str | None = None,
        voice: str | None = None,
        speed: int | None = None,
        prefer_daemon: bool = True,
    ) -> bool:
        """Speak text aloud.

        Args:
            text: Text to speak.
            engine: TTS engine override (espeak, say, piper, coqui, outetts).
            language: Language code override.
            voice: Voice name or speaker WAV path override.
            speed: Speech speed override (WPM).
            prefer_daemon: If True, use daemon when available (uses cached models).

        Returns:
            True if speech was successful.
        """
        # Use daemon if available and preferred
        if prefer_daemon and self._daemon_available():
            return self._speak_via_daemon(
                text,
                engine=engine,
                language=language,
                voice=voice,
                speed=speed,
            )

        # Fall back to local engine
        return self._speak_local(
            text,
            engine=engine,
            language=language,
            voice=voice,
            speed=speed,
        )

    def _speak_via_daemon(
        self,
        text: str,
        *,
        engine: str | None,
        language: str | None,
        voice: str | None,
        speed: int | None,
    ) -> bool:
        """Speak text via daemon.

        Args:
            text: Text to speak.
            engine: TTS engine name.
            language: Language code.
            voice: Voice name.
            speed: Speech speed.

        Returns:
            True if speech was successful.
        """
        from voxtype.daemon.client import DaemonClient
        from voxtype.daemon.protocol import ErrorResponse

        client = DaemonClient()
        response = client.send_tts_request(
            text=text,
            engine=engine,
            language=language,
            voice=voice,
            speed=speed,
        )

        if isinstance(response, ErrorResponse):
            return False

        return response.status == "ok"

    def _speak_local(
        self,
        text: str,
        *,
        engine: str | None,
        language: str | None,
        voice: str | None,
        speed: int | None,
    ) -> bool:
        """Speak text using local engine.

        Args:
            text: Text to speak.
            engine: TTS engine name override.
            language: Language code override.
            voice: Voice name override.
            speed: Speech speed override.

        Returns:
            True if speech was successful.
        """
        from voxtype.config import TTSConfig
        from voxtype.tts import get_cached_tts_engine

        # Build config with overrides
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
        *,
        prefer_daemon: bool = True,
    ) -> bool:
        """Speak text using a specific TTSConfig.

        Args:
            text: Text to speak.
            tts_config: TTS configuration to use.
            prefer_daemon: If True, use daemon when available.

        Returns:
            True if speech was successful.
        """
        return self.speak(
            text,
            engine=tts_config.engine,
            language=tts_config.language,
            voice=tts_config.voice,
            speed=tts_config.speed,
            prefer_daemon=prefer_daemon,
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
        from voxtype.config import TTSConfig
        from voxtype.tts import get_cached_tts_engine

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
