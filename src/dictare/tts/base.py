"""Base TTS interface and shared playback utilities."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


def play_wav_native(path: str | Path, *, timeout: float = 120.0) -> None:
    """Play a WAV file using the native system audio player.

    Uses afplay on macOS, paplay/aplay on Linux.  Native players handle
    sample-rate resampling correctly (no crackling).

    See docs/notes/audio-playback-architecture.md for rationale.

    Args:
        path: Path to WAV file.
        timeout: Maximum playback time in seconds.
    """
    path_str = str(path)

    if sys.platform == "darwin":
        subprocess.run(["afplay", path_str], capture_output=True, timeout=timeout)
    else:
        # Linux: prefer paplay (PipeWire/PulseAudio), fall back to aplay (ALSA)
        if shutil.which("paplay"):
            subprocess.run(
                ["paplay", path_str], capture_output=True, timeout=timeout,
            )
        elif shutil.which("aplay"):
            subprocess.run(
                ["aplay", "-q", path_str], capture_output=True, timeout=timeout,
            )
        else:
            logger.warning("No native audio player found (paplay/aplay)")


class TTSEngine(ABC):
    """Abstract text-to-speech interface."""

    @abstractmethod
    def speak(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> bool:
        """Speak text aloud.

        Args:
            text: Text to speak.
            voice: Per-request voice override (engine-dependent, optional).
            language: Per-request language override (engine-dependent, optional).

        Returns:
            True if successful.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if TTS engine is available."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get engine name."""
        pass

    def check_cache(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> Path | None:
        """Check if audio for *text* is already cached.

        Returns the WAV file path on cache hit, ``None`` on miss.
        Override in engines that support caching (e.g. Kokoro).
        """
        return None

    def list_voices(self) -> list[str]:
        """Return available voice names for this engine.

        Default: empty list (engine doesn't support voice listing).
        Override in subclasses that support it.
        """
        return []
