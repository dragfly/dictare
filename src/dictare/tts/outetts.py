"""OuteTTS backend - MLX-optimized TTS for Apple Silicon.

OuteTTS is a Llama-based TTS model that works reliably with mlx-audio.
This is the recommended TTS engine for Apple Silicon Macs.

GitHub: https://github.com/Blaizzy/mlx-audio
Models: https://huggingface.co/mlx-community (search "OuteTTS")
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

from dictare.tts.base import TTSEngine, play_audio_native
from dictare.tts.cache import cache_evict, cache_hit, cache_key, cache_save
from dictare.utils.hardware import is_apple_silicon

logger = logging.getLogger(__name__)

def _has_mlx_audio() -> bool:
    """Check if mlx-audio is available."""
    try:
        import mlx_audio  # noqa: F401
        return True
    except ImportError:
        return False

# Available OuteTTS models on mlx-community
OUTETTS_MODELS = {
    "small": ("mlx-community/Llama-OuteTTS-1.0-1B-4bit", 0.6),   # ~600MB
    "medium": ("mlx-community/Llama-OuteTTS-1.0-1B-8bit", 1.0),  # ~1GB
    "large": ("mlx-community/Llama-OuteTTS-1.0-1B-fp16", 2.0),   # ~2GB
}

# Supported languages (24 total)
SUPPORTED_LANGUAGES = [
    "en", "it", "de", "fr", "es", "pt", "nl",  # European
    "zh", "ja", "ko",  # East Asian
    "ar", "fa",  # Middle Eastern
    "ru", "uk", "be", "pl", "lt", "lv", "hu",  # Eastern European
    "bn", "ta", "sw", "ka",  # Other
]

# Additional model needed by OuteTTS
SNAC_MODEL = ("mlx-community/snac_24khz", 0.1)  # ~100MB

DEFAULT_MODEL = "small"

class OuteTTS(TTSEngine):
    """TTS using OuteTTS via mlx-audio - optimized for Apple Silicon.

    Install: ./install.sh (includes mlx-audio on Apple Silicon)

    Models (auto-downloaded on first use):
    - small: 4-bit quantized, fastest, ~600MB
    - medium: 8-bit quantized, balanced, ~1GB
    - large: fp16, best quality, ~2GB
    """

    def __init__(
        self,
        language: str = "en",
        speed: float = 1.0,
        voice: str = "",
        model_size: str = "small",
    ) -> None:
        """Initialize OuteTTS.

        Args:
            language: Language code (en, etc.).
            speed: Speech speed multiplier (0.5-2.0).
            voice: Voice name (model-specific, optional).
            model_size: Model size - "small", "medium", or "large".
        """
        self.language = language
        self.speed = speed
        self.voice = voice
        self.model_size = model_size

        model_info = OUTETTS_MODELS.get(model_size, OUTETTS_MODELS[DEFAULT_MODEL])
        self._model_repo = model_info[0]
        self._model_size_gb = model_info[1]

        self._available: bool | None = None
        self._models_ready: bool = False

    def is_available(self) -> bool:
        """Check if mlx-audio is available on Apple Silicon."""
        if self._available is not None:
            return self._available

        if not is_apple_silicon():
            self._available = False
            return False

        self._available = _has_mlx_audio()
        return self._available

    def _ensure_models_downloaded(self) -> bool:
        """Ensure models are downloaded with nice progress bar."""
        if self._models_ready:
            return True

        from huggingface_hub import snapshot_download

        from dictare.utils.hf_download import download_with_progress, is_repo_cached

        # Check and download main model
        if not is_repo_cached(self._model_repo, "config.json"):
            from rich.console import Console
            console = Console()

            console.print(f"[cyan]Downloading OuteTTS model ({self._model_size_gb:.1f} GB)...[/]")

            download_with_progress(
                self._model_repo,
                lambda: snapshot_download(self._model_repo),
                fallback_size_gb=self._model_size_gb,
            )

        # Check and download SNAC codec model (needed for audio decoding)
        snac_repo, snac_size = SNAC_MODEL
        if not is_repo_cached(snac_repo, "config.json"):
            from rich.console import Console
            console = Console()

            console.print(f"[cyan]Downloading audio codec ({snac_size:.1f} GB)...[/]")

            download_with_progress(
                snac_repo,
                lambda: snapshot_download(snac_repo),
                fallback_size_gb=snac_size,
            )

        self._models_ready = True
        return True

    def _cache_key(self, text: str) -> str:
        """Compute cache key using current model/language/voice."""
        return cache_key(
            f"outetts-{self.model_size}", text, self.language, self.voice,
        )

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
        volume: float = 1.0,
    ) -> bool:
        """Speak text using OuteTTS via mlx-audio.

        Per-request voice/language overrides are ignored (outetts uses
        config values set at init time).
        """
        if voice or language:
            logger.debug("outetts ignores per-request voice/language overrides")
        if not self.is_available():
            return False

        # Ensure models are downloaded with nice progress
        if not self._ensure_models_downloaded():
            return False

        try:
            key = self._cache_key(text)

            # Cache hit → play directly
            cached = cache_hit(key)
            if cached:
                logger.debug("TTS cache hit: %s", key[:12])
                play_audio_native(cached, timeout=120.0, volume=volume)
                return True

            # Cache miss → generate and cache
            return self._generate_and_cache(text, key, volume=volume)

        except Exception as e:
            logging.error(f"TTS exception: {e}")
            return False

    def _generate_and_cache(self, text: str, key: str, *, volume: float = 1.0) -> bool:
        """Generate audio, save to cache, and play."""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                logging.getLogger("transformers").setLevel(logging.ERROR)
                logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

                with tempfile.TemporaryDirectory() as tmpdir:
                    cmd = [
                        sys.executable, "-m", "mlx_audio.tts.generate",
                        "--model", self._model_repo,
                        "--text", text,
                        "--speed", str(self.speed),
                        "--lang_code", self.language,
                        "--file_prefix", f"{tmpdir}/audio",
                    ]

                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        timeout=120,
                        env={**os.environ, "TQDM_DISABLE": "1"},
                    )

                    if result.returncode != 0:
                        logging.error(f"TTS generation failed: {result.stderr.decode()}")
                        return False

                    audio_files = list(Path(tmpdir).glob("audio_*.wav"))
                    if not audio_files:
                        return False

                    # Save to cache → play → evict
                    cached_path = cache_save(key, audio_files[0])
                    play_audio_native(cached_path, timeout=120.0, volume=volume)
                    cache_evict()
                    return True

        except Exception as e:
            logging.error(f"TTS exception: {e}")
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return f"outetts-{self.model_size}"
