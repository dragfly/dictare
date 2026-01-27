"""Text-to-speech module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from voxtype.tts.base import TTSEngine
from voxtype.tts.coqui import CoquiTTS
from voxtype.tts.espeak import EspeakTTS
from voxtype.tts.piper import PiperTTS
from voxtype.tts.say import SayTTS

if TYPE_CHECKING:
    from voxtype.config import TTSConfig

__all__ = ["TTSEngine", "CoquiTTS", "EspeakTTS", "PiperTTS", "SayTTS", "create_tts_engine"]


def create_tts_engine(config: TTSConfig) -> TTSEngine:
    """Create TTS engine from configuration.

    Args:
        config: TTS configuration.

    Returns:
        Configured TTS engine instance.

    Raises:
        ValueError: If engine type is unknown or unavailable.
    """
    engine_map = {
        "espeak": lambda: EspeakTTS(
            language=config.language,
            speed=config.speed,
        ),
        "say": lambda: SayTTS(
            language=config.language,
            speed=config.speed,
            voice=config.voice,
        ),
        "piper": lambda: PiperTTS(
            language=config.language,
            speed=config.speed,
            voice=config.voice,
        ),
        "coqui": lambda: CoquiTTS(
            language=config.language,
            speed=config.speed,
            voice=config.voice,
        ),
    }

    if config.engine not in engine_map:
        raise ValueError(f"Unknown TTS engine: {config.engine}")

    engine = engine_map[config.engine]()

    if not engine.is_available():
        raise ValueError(
            f"TTS engine '{config.engine}' is not available. "
            f"Check installation requirements."
        )

    return engine
