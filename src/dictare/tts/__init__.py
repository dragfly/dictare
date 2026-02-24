"""Text-to-speech module."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from dictare.tts.base import TTSEngine
from dictare.tts.coqui import CoquiTTS
from dictare.tts.espeak import EspeakTTS
from dictare.tts.outetts import OuteTTS
from dictare.tts.piper import PiperTTS
from dictare.tts.say import SayTTS

if TYPE_CHECKING:
    from dictare.config import TTSConfig

__all__ = [
    "TTSEngine",
    "CoquiTTS",
    "EspeakTTS",
    "OuteTTS",
    "PiperTTS",
    "SayTTS",
    "create_tts_engine",
    "get_cached_tts_engine",
    "clear_tts_cache",
]

# TTS engine cache
_tts_cache: dict[str, TTSEngine] = {}
_tts_cache_lock = threading.Lock()


def _make_cache_key(config: TTSConfig) -> str:
    """Create cache key from TTS config."""
    return f"{config.engine}:{config.language}:{config.voice}:{config.speed}"


def get_cached_tts_engine(config: TTSConfig) -> TTSEngine:
    """Get or create cached TTS engine.

    Args:
        config: TTS configuration.

    Returns:
        Cached or newly created TTS engine.

    Raises:
        ValueError: If engine type is unknown or unavailable.
    """
    key = _make_cache_key(config)

    with _tts_cache_lock:
        if key not in _tts_cache:
            _tts_cache[key] = create_tts_engine(config)
        return _tts_cache[key]


def clear_tts_cache() -> None:
    """Clear the TTS engine cache."""
    with _tts_cache_lock:
        _tts_cache.clear()


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
        "outetts": lambda: OuteTTS(
            language=config.language,
            speed=1.0,  # OuteTTS uses multiplier (1.0), not WPM
            voice="",   # Don't pass voice, use model default
        ),
    }

    if config.engine not in engine_map:
        raise ValueError(f"Unknown TTS engine: {config.engine}")

    engine = engine_map[config.engine]()

    if not engine.is_available():
        from dictare.utils.install_info import get_feature_install_message

        # System commands (not pip installable)
        system_hints = {
            "espeak": "Install: sudo apt install espeak (Linux) or brew install espeak (macOS)",
            "say": "Only available on macOS",
        }

        if config.engine in system_hints:
            hint = system_hints[config.engine]
        else:
            # Use the install info system for pip-installable engines
            hint = get_feature_install_message(config.engine)

        raise ValueError(f"TTS engine '{config.engine}' is not available.\n{hint}")

    return engine
