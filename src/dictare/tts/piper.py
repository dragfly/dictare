"""Piper TTS backend - fast neural text-to-speech."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from dictare.tts.base import TTSEngine, play_audio_native
from dictare.tts.cache import cache_evict, cache_hit, cache_key, cache_save

logger = logging.getLogger(__name__)

# Voice models directory
_VOICES_DIR = Path.home() / ".local" / "share" / "piper-voices"

# HuggingFace base URL for piper voice models
_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

class PiperTTS(TTSEngine):
    """TTS using Piper - fast, local neural TTS.

    Piper is a fast, local neural text-to-speech system.
    Install: pip install piper-tts
    Models: https://github.com/rhasspy/piper#voices

    Voice models are downloaded automatically on first use.
    """

    # Default voices per language (small, fast models)
    DEFAULT_VOICES = {
        "en": "en_US-lessac-medium",
        "es": "es_ES-davefx-medium",
        "de": "de_DE-thorsten-medium",
        "it": "it_IT-riccardo-x_low",
        "fr": "fr_FR-siwis-medium",
    }

    def __init__(self, language: str = "en", speed: int = 175, voice: str = "") -> None:
        """Initialize Piper TTS.

        Args:
            language: Language code (en, it, de, etc.).
            speed: Ignored for Piper (speed is model-dependent).
            voice: Piper voice model name. Empty = auto-select based on language.
        """
        self.language = language
        self.voice = voice or self.DEFAULT_VOICES.get(language, "en_US-lessac-medium")
        self._piper_cmd = self._detect_piper()

    def _detect_piper(self) -> str | None:
        """Detect piper command."""
        import sys

        # Try piper in PATH
        if shutil.which("piper"):
            return "piper"
        if shutil.which("piper-tts"):
            return "piper-tts"

        # Try piper in the same directory as Python executable
        # This handles uv tool installations where scripts aren't in PATH
        python_bin = Path(sys.executable).parent
        piper_path = python_bin / "piper"
        if piper_path.exists():
            return str(piper_path)

        # Try piper in the isolated TTS venv
        from dictare.tts.venv import get_venv_bin_dir

        venv_bin = get_venv_bin_dir("piper")
        if venv_bin:
            venv_piper = venv_bin / "piper"
            if venv_piper.exists():
                return str(venv_piper)

        return None

    def _get_model_path(self) -> Path:
        """Get path to voice model ONNX file, downloading if needed.

        Voice is best-effort: if the requested voice cannot be downloaded,
        falls back to the language default and tries again.
        """
        path = self._download_voice(self.voice)
        if path:
            return path

        # Fallback to language default
        default_voice = self.DEFAULT_VOICES.get(self.language, "en_US-lessac-medium")
        if default_voice != self.voice:
            logger.warning(
                "Voice %r unavailable, falling back to %r", self.voice, default_voice,
            )
            self.voice = default_voice
            path = self._download_voice(default_voice)
            if path:
                return path

        raise RuntimeError(f"Failed to download any Piper voice for language {self.language!r}")

    @staticmethod
    def _download_voice(voice: str) -> Path | None:
        """Download a voice model from HuggingFace. Returns path or None on failure."""
        model_path = _VOICES_DIR / f"{voice}.onnx"
        if model_path.exists():
            return model_path

        _VOICES_DIR.mkdir(parents=True, exist_ok=True)

        # Voice name format: en_US-lessac-medium → en/en_US/lessac/medium/
        parts = voice.split("-")
        lang_region = parts[0]  # e.g., "en_US"
        lang = lang_region.split("_")[0]  # e.g., "en"
        name = parts[1] if len(parts) > 1 else "default"
        quality = parts[2] if len(parts) > 2 else "medium"
        hf_path = f"{lang}/{lang_region}/{name}/{quality}"

        import urllib.request

        for suffix in [".onnx", ".onnx.json"]:
            url = f"{_HF_BASE}/{hf_path}/{voice}{suffix}"
            dest = _VOICES_DIR / f"{voice}{suffix}"
            logger.info("Downloading piper voice: %s", url)
            try:
                urllib.request.urlretrieve(url, dest)
            except Exception:
                logger.warning("Failed to download %s", url)
                dest.unlink(missing_ok=True)
                return None

        return model_path

    def is_available(self) -> bool:
        """Check if piper is available."""
        return self._piper_cmd is not None

    def _cache_key(self, text: str) -> str:
        """Compute cache key using resolved voice/language."""
        return cache_key("piper", text, self.language, self.voice)

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
        """Speak text using Piper.

        Per-request voice/language overrides are ignored (piper uses
        config values set at init time).
        """
        if voice or language:
            logger.debug("piper ignores per-request voice/language overrides")
        if not self._piper_cmd:
            return False

        try:
            model_path = self._get_model_path()
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

            result = subprocess.run(
                [
                    self._piper_cmd,
                    "--model", str(model_path),
                    "--output_file", str(wav_path),
                ],
                input=text.encode(),
                capture_output=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.warning("Piper failed: %s", result.stderr.decode()[:200])
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
            logger.warning("Piper speak failed", exc_info=True)
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return "piper"
