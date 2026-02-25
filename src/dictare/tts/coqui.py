"""Coqui XTTS TTS backend - high-quality neural text-to-speech."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dictare.tts.base import TTSEngine, play_audio_native
from dictare.tts.cache import cache_evict, cache_hit, cache_key, cache_save

logger = logging.getLogger(__name__)

# XTTS v2: multilingual model, supports --language_idx and --speaker_wav
_XTTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"


class CoquiTTS(TTSEngine):
    """TTS using Coqui TTS / XTTS - high-quality neural voices.

    Coqui TTS provides state-of-the-art neural text-to-speech.
    Install: pip install TTS

    The first run will download the model (~1.5GB for XTTS v2).
    Supports voice cloning from audio samples.
    """

    # Language codes supported by XTTS v2
    SUPPORTED_LANGUAGES = {"en", "es", "de", "it", "fr", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh", "ja", "ko", "hu"}

    def __init__(self, language: str = "en", speed: int = 175, voice: str = "") -> None:
        """Initialize Coqui TTS.

        Args:
            language: Language code (en, es, de, it, fr, etc.).
            speed: Ignored for Coqui (not adjustable via CLI).
            voice: Path to speaker WAV file for voice cloning (optional).
        """
        self.language = language if language in self.SUPPORTED_LANGUAGES else "en"
        self.voice = voice  # Path to reference audio for voice cloning
        self._tts_cmd = self._detect_tts()

    def _detect_tts(self) -> str | None:
        """Detect tts command (Coqui TTS CLI)."""
        import sys

        # Try tts in PATH
        if shutil.which("tts"):
            return "tts"

        # Try tts in the same directory as Python executable
        # This handles uv tool installations where scripts aren't in PATH
        python_bin = Path(sys.executable).parent
        tts_path = python_bin / "tts"
        if tts_path.exists():
            return str(tts_path)

        # Try tts in the isolated TTS venv
        from dictare.tts.venv import get_venv_bin_dir

        venv_bin = get_venv_bin_dir("coqui")
        if venv_bin:
            venv_tts = venv_bin / "tts"
            if venv_tts.exists():
                return str(venv_tts)

        return None

    def is_available(self) -> bool:
        """Check if Coqui TTS is available."""
        return self._tts_cmd is not None

    def _cache_key(self, text: str) -> str:
        """Compute cache key using current language/voice."""
        return cache_key("coqui", text, self.language, self.voice)

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
    ) -> bool:
        """Speak text using Coqui TTS.

        Per-request voice/language overrides are ignored (coqui uses
        config values set at init time).
        """
        if voice or language:
            logger.debug("coqui ignores per-request voice/language overrides")
        if not self._tts_cmd:
            return False

        try:
            key = self._cache_key(text)

            # Cache hit → play directly
            cached = cache_hit(key)
            if cached:
                logger.debug("TTS cache hit: %s", key[:12])
                play_audio_native(cached, timeout=120.0)
                return True

            # Cache miss → generate
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = Path(f.name)

            # Build command — always use XTTS v2 for multilingual support.
            cmd = [
                self._tts_cmd,
                "--model_name", _XTTS_MODEL,
                "--text", text,
                "--language_idx", self.language,
                "--out_path", str(wav_path),
            ]

            # Add speaker reference for voice cloning if provided
            if self.voice and Path(self.voice).exists():
                cmd.extend(["--speaker_wav", self.voice])

            # Generate audio — accept Coqui license automatically
            env = {**os.environ, "COQUI_TOS_AGREED": "1"}
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,
                env=env,
            )

            if result.returncode != 0 or not wav_path.exists():
                stderr = result.stderr.decode(errors="replace")[:500] if result.stderr else ""
                logger.warning("Coqui TTS failed (exit %d): %s", result.returncode, stderr)
                wav_path.unlink(missing_ok=True)
                return False

            # Save to cache → play → evict
            try:
                cached_path = cache_save(key, wav_path)
                play_audio_native(cached_path, timeout=120.0)
                cache_evict()
            finally:
                wav_path.unlink(missing_ok=True)

            return True

        except Exception:
            logger.warning("Coqui TTS exception", exc_info=True)
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return "coqui"
