"""Piper TTS backend - fast neural text-to-speech."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from voxtype.tts.base import TTSEngine

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

    def is_available(self) -> bool:
        """Check if piper is available."""
        return self._piper_cmd is not None

    def speak(self, text: str) -> bool:
        """Speak text using Piper + aplay/afplay.

        Args:
            text: Text to speak.

        Returns:
            True if successful.
        """
        if not self._piper_cmd:
            return False

        try:
            import sys

            # Create temp file for audio
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = Path(f.name)

            # Generate audio with piper
            result = subprocess.run(
                [
                    self._piper_cmd,
                    "--model", self.voice,
                    "--output_file", str(wav_path),
                ],
                input=text.encode(),
                capture_output=True,
                timeout=60,
            )

            if result.returncode != 0:
                wav_path.unlink(missing_ok=True)
                return False

            # Play audio
            if sys.platform == "darwin":
                player = ["afplay", str(wav_path)]
            else:
                player = ["aplay", "-q", str(wav_path)]

            subprocess.run(player, capture_output=True, timeout=120)
            wav_path.unlink(missing_ok=True)
            return True

        except Exception:
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return "piper"
