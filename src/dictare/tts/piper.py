"""Piper TTS backend - fast neural text-to-speech."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from dictare.tts.base import TTSEngine

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

        return None

    def _get_model_path(self) -> Path:
        """Get path to voice model ONNX file, downloading if needed."""
        model_path = _VOICES_DIR / f"{self.voice}.onnx"
        if model_path.exists():
            return model_path

        # Download model and config from HuggingFace
        _VOICES_DIR.mkdir(parents=True, exist_ok=True)

        # Voice name format: en_US-lessac-medium → en/en_US/lessac/medium/
        parts = self.voice.split("-")
        lang_region = parts[0]  # e.g., "en_US"
        lang = lang_region.split("_")[0]  # e.g., "en"
        name = parts[1] if len(parts) > 1 else "default"
        quality = parts[2] if len(parts) > 2 else "medium"
        hf_path = f"{lang}/{lang_region}/{name}/{quality}"

        for suffix in [".onnx", ".onnx.json"]:
            url = f"{_HF_BASE}/{hf_path}/{self.voice}{suffix}"
            dest = _VOICES_DIR / f"{self.voice}{suffix}"
            logger.info("Downloading piper voice: %s", url)
            try:
                import urllib.request
                urllib.request.urlretrieve(url, dest)
            except Exception:
                logger.warning("Failed to download %s", url)
                dest.unlink(missing_ok=True)
                raise

        return model_path

    def is_available(self) -> bool:
        """Check if piper is available."""
        return self._piper_cmd is not None

    def speak(self, text: str) -> bool:
        """Speak text using Piper.

        On macOS, plays via afplay (native CoreAudio resampling).
        On Linux, plays via the serialized sounddevice audio worker.

        Args:
            text: Text to speak.

        Returns:
            True if successful.
        """
        import sys

        if not self._piper_cmd:
            return False

        try:
            model_path = self._get_model_path()

            # Create temp file for audio
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = Path(f.name)

            # Generate audio with piper
            result = subprocess.run(
                [
                    self._piper_cmd,
                    "--model", str(model_path),
                    "--output_file", str(wav_path),
                ],
                input=text.encode(),
                capture_output=True,
                timeout=60,
            )

            if result.returncode != 0:
                logger.warning("Piper failed: %s", result.stderr.decode()[:200])
                wav_path.unlink(missing_ok=True)
                return False

            # Play audio
            if sys.platform == "darwin":
                # afplay handles CoreAudio resampling natively (no crackling)
                subprocess.run(
                    ["afplay", str(wav_path)],
                    capture_output=True,
                    timeout=120,
                )
            else:
                # Linux: use serialized sounddevice worker (thread-safe)
                from dictare.audio.beep import play_wav_sync

                play_wav_sync(wav_path, timeout_s=120)

            wav_path.unlink(missing_ok=True)
            return True

        except Exception:
            logger.warning("Piper speak failed", exc_info=True)
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return "piper"
