"""macOS 'say' TTS backend."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dictare.tts.base import TTSEngine, play_wav_native
from dictare.tts.cache import cache_evict, cache_hit, cache_key, cache_save

logger = logging.getLogger(__name__)


class SayTTS(TTSEngine):
    """TTS using macOS built-in 'say' command."""

    def __init__(self, language: str = "en", speed: int = 175, voice: str = "") -> None:
        """Initialize macOS say TTS.

        Args:
            language: Language code (used to select appropriate voice if voice is empty).
            speed: Speech rate in words per minute (90-720, default 175).
            voice: Voice name (e.g., 'Samantha', 'Daniel'). Empty = system default.
        """
        self.language = language
        self.speed = max(90, min(720, speed))  # Clamp to valid range
        self.voice = voice

    def is_available(self) -> bool:
        """Check if say is available (macOS only)."""
        return sys.platform == "darwin" and shutil.which("say") is not None

    def _cache_key(self, text: str) -> str:
        """Compute cache key using current voice/speed."""
        return cache_key("say", text, self.language, f"{self.voice}@{self.speed}")

    def check_cache(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> Path | None:
        """Check if audio for *text* is cached. Returns path or None."""
        return cache_hit(self._cache_key(text))

    def speak(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> bool:
        """Speak text using macOS say.

        Per-request voice/language overrides are ignored (say uses
        config values set at init time).
        """
        if voice or language:
            logger.debug("say ignores per-request voice/language overrides")
        if not self.is_available():
            logger.warning("say: not available (platform=%s)", sys.platform)
            return False

        try:
            key = self._cache_key(text)

            # Cache hit → play directly
            cached = cache_hit(key)
            if cached:
                logger.debug("TTS cache hit: %s", key[:12])
                play_wav_native(cached, timeout=120.0)
                return True

            # Cache miss → generate audio file (macOS say only writes AIFF)
            with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as f:
                wav_path = Path(f.name)

            cmd = ["say", "-r", str(self.speed), "-o", str(wav_path)]
            if self.voice:
                cmd.extend(["-v", self.voice])
            cmd.append(text)

            result = subprocess.run(cmd, capture_output=True, timeout=120)
            if result.returncode != 0:
                logger.warning(
                    "say exited %d: %s",
                    result.returncode,
                    result.stderr.decode(errors="replace").strip(),
                )
                wav_path.unlink(missing_ok=True)
                return False

            # Save to cache → play → evict
            try:
                cached_path = cache_save(key, wav_path)
                play_wav_native(cached_path, timeout=120.0)
                cache_evict()
            finally:
                wav_path.unlink(missing_ok=True)

            return True
        except Exception:
            logger.warning("say subprocess failed", exc_info=True)
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return "say"

    def list_voices(self) -> list[str]:
        """Return available macOS voices."""
        if not self.is_available():
            return []
        try:
            result = subprocess.run(
                ["say", "-v", "?"], capture_output=True, text=True, timeout=10,
            )
            # Format: "Name  lang_code  # description"
            return sorted(
                line.split()[0] for line in result.stdout.splitlines() if line.strip()
            )
        except Exception:
            return []
