"""Kokoro TTS backend — lightweight ONNX neural TTS.

Kokoro is a 82M-parameter TTS model, #1 on HuggingFace TTS Arena.
Uses kokoro-onnx (ONNX runtime, no PyTorch). Supports 9 languages
(EN, IT, ES, FR, JA, ZH...), ~300MB model, 5x real-time on CPU.
Bundles espeak-ng phonemizer. MIT/Apache 2.0.

GitHub: https://github.com/remsky/kokoro-onnx
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from dictare.tts.base import TTSEngine, play_wav_native

logger = logging.getLogger(__name__)

# Language code mapping: dictare language → kokoro lang code
_LANG_MAP: dict[str, str] = {
    "en": "en-us",
    "en-us": "en-us",
    "en-gb": "en-gb",
    "es": "es",
    "fr": "fr-fr",
    "it": "it",
    "pt": "pt-br",
    "ja": "ja",
    "zh": "zh",
    "hi": "hi",
}

# Default voice per language family
_DEFAULT_VOICES: dict[str, str] = {
    "en": "af_heart",
    "es": "ef_dora",
    "fr": "ff_siwis",
    "it": "if_sara",
    "pt": "pf_dora",
    "ja": "jf_alpha",
    "zh": "zf_xiaobei",
    "hi": "hf_alpha",
}


class KokoroTTS(TTSEngine):
    """TTS using Kokoro via kokoro-onnx — lightweight ONNX runtime.

    Install via Dashboard or: pip install kokoro-onnx soundfile

    Model (~300MB) auto-downloaded on first use from GitHub releases.
    """

    def __init__(
        self,
        language: str = "en",
        speed: float = 1.0,
        voice: str = "af_heart",
    ) -> None:
        """Initialize KokoroTTS.

        Args:
            language: Language code (en, it, es, fr, ja, zh, etc.).
            speed: Speech speed multiplier (0.5-2.0, 1.0 = normal).
            voice: Kokoro voice name (e.g., af_heart, bf_emma).
        """
        self.language = language
        self.speed = speed
        self.voice = voice
        self._kokoro: object | None = None  # lazy-loaded Kokoro instance
        self._available: bool | None = None

    def is_available(self) -> bool:
        """Check if kokoro-onnx is importable."""
        if self._available is not None:
            return self._available
        try:
            import kokoro_onnx  # noqa: F401

            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def _get_kokoro(self) -> object:
        """Lazy-load and cache the Kokoro model instance."""
        if self._kokoro is not None:
            return self._kokoro

        from kokoro_onnx import Kokoro

        model_dir = self._model_dir()
        model_path = model_dir / "model.onnx"
        voices_path = model_dir / "voices.bin"

        if not model_path.exists() or not voices_path.exists():
            self._download_model(model_dir)

        self._kokoro = Kokoro(str(model_path), str(voices_path))
        return self._kokoro

    @staticmethod
    def _model_dir() -> Path:
        """Return the directory for kokoro model files."""
        return Path.home() / ".local" / "share" / "dictare" / "models" / "kokoro"

    @staticmethod
    def _download_model(model_dir: Path) -> None:
        """Download kokoro model files from GitHub releases."""
        import urllib.request

        model_dir.mkdir(parents=True, exist_ok=True)

        base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
        files = {
            "model.onnx": f"{base}/kokoro-v1.0.onnx",
            "voices.bin": f"{base}/voices-v1.0.bin",
        }

        for filename, url in files.items():
            dest = model_dir / filename
            if dest.exists():
                continue
            logger.info("Downloading kokoro %s (~%s)...", filename, "310MB" if "model" in filename else "27MB")
            urllib.request.urlretrieve(url, str(dest))
            logger.info("Downloaded %s", filename)

    @staticmethod
    def _resolve_lang(language: str) -> str:
        """Map dictare language code to kokoro lang code."""
        lang = language.lower()
        if lang in _LANG_MAP:
            return _LANG_MAP[lang]
        # Try base language (e.g., "en-au" → "en")
        base = lang.split("-")[0]
        if base in _LANG_MAP:
            return _LANG_MAP[base]
        # Fallback to en-us
        return "en-us"

    @staticmethod
    def _resolve_voice(language: str, voice: str) -> str:
        """Pick voice: user-specified, or language-appropriate default."""
        if voice:
            return voice
        base = language.lower().split("-")[0]
        return _DEFAULT_VOICES.get(base, "af_heart")

    def _get_cache_key(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> tuple[str, str, str]:
        """Return (cache_key, kokoro_lang, resolved_voice) for *text*."""
        from dictare.tts.cache import cache_key

        lang, resolved_voice = self._resolve_params(voice=voice, language=language)
        return cache_key("kokoro", text, lang, resolved_voice), lang, resolved_voice

    def check_cache(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> Path | None:
        """Check if audio for *text* is cached. Returns WAV path or None."""
        from dictare.tts.cache import cache_hit

        key, _, _ = self._get_cache_key(text, voice=voice, language=language)
        return cache_hit(key)

    def _resolve_params(
        self,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> tuple[str, str]:
        """Resolve lang/voice with optional per-request overrides.

        Returns (kokoro_lang, resolved_voice). Pure — no instance mutation.
        """
        lang = language or self.language
        v = voice or self.voice
        return self._resolve_lang(lang), self._resolve_voice(lang, v)

    def speak(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> bool:
        """Speak text using Kokoro.

        Args:
            text: Text to speak.
            voice: Per-request voice override.
            language: Per-request language override.

        Returns:
            True if successful.
        """
        if not self.is_available():
            return False

        try:
            from dictare.tts.cache import cache_evict, cache_hit, cache_save

            key, lang, resolved_voice = self._get_cache_key(
                text, voice=voice, language=language,
            )

            # Cache check
            cached = cache_hit(key)
            if cached:
                logger.debug("TTS cache hit: %s", key[:12])
                play_wav_native(cached, timeout=120.0)
                return True

            # Cache miss — generate
            import soundfile as sf

            kokoro = self._get_kokoro()

            # kokoro.create() returns (samples, sample_rate)
            samples, sample_rate = kokoro.create(  # type: ignore[attr-defined]
                text,
                voice=resolved_voice,
                speed=self.speed,
                lang=lang,
            )

            # Write to temp WAV → save to cache → play
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            sf.write(str(tmp_path), samples, sample_rate)
            try:
                cached_path = cache_save(key, tmp_path)
                play_wav_native(cached_path, timeout=120.0)
                cache_evict()
            finally:
                tmp_path.unlink(missing_ok=True)

            return True

        except Exception as exc:
            logger.error("Kokoro TTS failed: %s", exc)
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return "kokoro"

    def list_voices(self) -> list[str]:
        """Return available voice names from the loaded model."""
        try:
            kokoro = self._get_kokoro()
            return sorted(kokoro.voices.keys())  # type: ignore[attr-defined]
        except Exception:
            return []
