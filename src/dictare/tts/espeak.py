"""eSpeak TTS backend."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from dictare.tts.base import TTSEngine, play_audio_native
from dictare.tts.cache import cache_evict, cache_hit, cache_key, cache_save

logger = logging.getLogger(__name__)


class EspeakTTS(TTSEngine):
    """TTS using espeak/espeak-ng."""

    def __init__(self, language: str = "it", speed: int = 160) -> None:
        """Initialize espeak TTS.

        Args:
            language: Language code (it, en, de, etc.).
            speed: Speech speed in words per minute (default 160).
        """
        self.language = language
        self.speed = speed
        self._cmd = self._detect_espeak()

    def _detect_espeak(self) -> str | None:
        """Detect espeak or espeak-ng (stores full path for daemon safety)."""
        path = shutil.which("espeak-ng")
        if path:
            return path
        path = shutil.which("espeak")
        if path:
            return path
        # Fallback: launchd services don't inherit Homebrew PATH
        for fallback in ("/opt/homebrew/bin/espeak-ng", "/usr/local/bin/espeak-ng"):
            if Path(fallback).exists():
                return fallback
        return None

    def is_available(self) -> bool:
        """Check if espeak is available."""
        return self._cmd is not None

    def _cache_key(self, text: str) -> str:
        """Compute cache key using current language/speed."""
        return cache_key("espeak", text, self.language, str(self.speed))

    def check_cache(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> Path | None:
        """Check if audio for *text* is cached. Returns WAV path or None."""
        return cache_hit(self._cache_key(text))

    def speak(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
        play: bool = True,
    ) -> bool:
        """Speak text using espeak.

        Per-request voice/language overrides are ignored (espeak uses
        config values set at init time).

        Args:
            text: Text to speak.
            voice: Ignored (uses init value).
            language: Ignored (uses init value).
            play: If False, generate and cache only (no playback).
        """
        if voice or language:
            logger.debug("espeak ignores per-request voice/language overrides")
        if not self._cmd:
            logger.warning("espeak: no binary found")
            return False

        try:
            key = self._cache_key(text)

            # Cache hit → play directly (or skip if play=False)
            cached = cache_hit(key)
            if cached:
                logger.debug("TTS cache hit: %s", key[:12])
                if play:
                    play_audio_native(cached, timeout=120.0)
                return True

            # Cache miss → generate WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = Path(f.name)

            result = subprocess.run(
                [
                    self._cmd,
                    "-v", self.language,
                    "-s", str(self.speed),
                    "-w", str(wav_path),
                    text,
                ],
                capture_output=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.warning(
                    "espeak exited %d: %s",
                    result.returncode,
                    result.stderr.decode(errors="replace").strip(),
                )
                wav_path.unlink(missing_ok=True)
                return False

            # Save to cache → play (if requested) → evict
            try:
                cached_path = cache_save(key, wav_path)
                if play:
                    play_audio_native(cached_path, timeout=120.0)
                cache_evict()
            finally:
                wav_path.unlink(missing_ok=True)

            return True
        except Exception:
            logger.warning("espeak subprocess failed", exc_info=True)
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return self._cmd or "espeak"
