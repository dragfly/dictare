"""VyvoTTS backend - Qwen3-based TTS via mlx-audio.

Note: On Apple Silicon, the 'qwen3' engine in mlx-audio uses VyvoTTS
(a Qwen3-based model), not the official Alibaba Qwen3-TTS.

For official Qwen3-TTS, use OuteTTS instead (better support in mlx-audio).

MLX: https://github.com/Blaizzy/mlx-audio
VyvoTTS: https://huggingface.co/Vyvo
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any

from voxtype.tts.base import TTSEngine

def _is_apple_silicon() -> bool:
    """Check if running on Apple Silicon."""
    if sys.platform != "darwin":
        return False
    import platform
    return platform.machine() == "arm64"

def _has_mlx_audio() -> bool:
    """Check if mlx-audio is available."""
    try:
        import mlx_audio  # noqa: F401
        return True
    except ImportError:
        return False

# VyvoTTS models on mlx-community (these work with mlx-audio's 'qwen3' architecture)
VYVO_MODELS = {
    "4bit": ("mlx-community/VyvoTTS-EN-Beta-4bit", 1.0),   # ~1GB, fastest
    "8bit": ("mlx-community/VyvoTTS-EN-Beta-8bit", 1.5),   # ~1.5GB, better quality
    "fp16": ("mlx-community/VyvoTTS-EN-Beta-fp16", 3.0),   # ~3GB, best quality
}

DEFAULT_MODEL = "4bit"

class Qwen3TTS(TTSEngine):
    """TTS using VyvoTTS via mlx-audio (Qwen3-based architecture).

    Note: This uses VyvoTTS, not the official Alibaba Qwen3-TTS.
    VyvoTTS is a Qwen3-based TTS model that works well with mlx-audio.

    Install: ./install.sh (includes mlx-audio on Apple Silicon)

    Models (auto-downloaded on first use):
    - 4bit: Fastest, ~300MB
    - 8bit: Better quality, ~500MB
    - fp16: Best quality, ~2GB
    """

    def __init__(
        self,
        language: str = "en",
        speed: float = 1.0,
        voice: str = "",
        model_size: str = DEFAULT_MODEL,
    ) -> None:
        """Initialize VyvoTTS (via qwen3 engine).

        Args:
            language: Language code (en only for VyvoTTS).
            speed: Speech speed multiplier (0.5-2.0).
            voice: Ignored (VyvoTTS uses single voice).
            model_size: Quantization - "4bit", "8bit", or "fp16".
        """
        self.language = language
        self.speed = speed
        self.voice = voice
        self.model_size = model_size if model_size in VYVO_MODELS else DEFAULT_MODEL

        model_info = VYVO_MODELS.get(self.model_size, VYVO_MODELS[DEFAULT_MODEL])
        self._model_repo = model_info[0]
        self._model_size_gb = model_info[1]

        self._available: bool | None = None
        self._models_ready: bool = False

    def is_available(self) -> bool:
        """Check if mlx-audio is available on Apple Silicon."""
        if self._available is not None:
            return self._available

        if not _is_apple_silicon():
            self._available = False
            return False

        self._available = _has_mlx_audio()
        return self._available

    def _ensure_models_downloaded(self) -> bool:
        """Ensure models are downloaded with nice progress bar."""
        if self._models_ready:
            return True

        from voxtype.utils.hf_download import is_repo_cached, download_with_progress
        from huggingface_hub import snapshot_download

        if not is_repo_cached(self._model_repo, "config.json"):
            download_with_progress(
                self._model_repo,
                lambda: snapshot_download(self._model_repo),
                fallback_size_gb=self._model_size_gb,
            )

        self._models_ready = True
        return True

    def speak(self, text: str) -> bool:
        """Speak text using VyvoTTS via mlx-audio CLI.

        Args:
            text: Text to speak.

        Returns:
            True if successful.
        """
        if not self.is_available():
            return False

        if not self._ensure_models_downloaded():
            return False

        return self._generate_and_play(text)

    def _generate_and_play(self, text: str) -> bool:
        """Generate audio and play it using mlx-audio CLI."""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                from huggingface_hub.utils import disable_progress_bars, enable_progress_bars
                disable_progress_bars()

                logging.getLogger("transformers").setLevel(logging.ERROR)
                logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

                try:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        cmd = [
                            sys.executable, "-m", "mlx_audio.tts.generate",
                            "--model", self._model_repo,
                            "--text", text,
                            "--speed", str(self.speed),
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
                        if audio_files:
                            subprocess.run(
                                ["afplay", str(audio_files[0])],
                                capture_output=True,
                                timeout=60,
                            )
                            return True

                        return False

                finally:
                    enable_progress_bars()

        except Exception as e:
            logging.error(f"TTS exception: {e}")
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return f"vyvotts-{self.model_size}"
