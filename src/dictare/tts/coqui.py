"""Coqui XTTS TTS backend - high-quality neural text-to-speech."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from dictare.tts.base import TTSEngine, play_wav_native


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

        return None

    def is_available(self) -> bool:
        """Check if Coqui TTS is available."""
        return self._tts_cmd is not None

    def speak(self, text: str) -> bool:
        """Speak text using Coqui TTS.

        Args:
            text: Text to speak.

        Returns:
            True if successful.
        """
        if not self._tts_cmd:
            return False

        try:
            # Create temp file for audio
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = Path(f.name)

            # Build command
            cmd = [
                self._tts_cmd,
                "--text", text,
                "--language_idx", self.language,
                "--out_path", str(wav_path),
            ]

            # Add speaker reference for voice cloning if provided
            if self.voice and Path(self.voice).exists():
                cmd.extend(["--speaker_wav", self.voice])

            # Generate audio
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,  # TTS can be slow on first run (model download)
            )

            if result.returncode != 0 or not wav_path.exists():
                wav_path.unlink(missing_ok=True)
                return False

            # Play via native system player
            play_wav_native(wav_path)
            wav_path.unlink(missing_ok=True)
            return True

        except Exception:
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return "coqui"
