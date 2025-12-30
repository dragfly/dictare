"""eSpeak TTS backend."""

from __future__ import annotations

import shutil
import subprocess

from voxtype.tts.base import TTSEngine

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
        """Detect espeak or espeak-ng."""
        if shutil.which("espeak-ng"):
            return "espeak-ng"
        if shutil.which("espeak"):
            return "espeak"
        return None

    def is_available(self) -> bool:
        """Check if espeak is available."""
        return self._cmd is not None

    def speak(self, text: str) -> bool:
        """Speak text using espeak.

        Args:
            text: Text to speak.

        Returns:
            True if successful.
        """
        if not self._cmd:
            return False

        try:
            subprocess.run(
                [
                    self._cmd,
                    "-v", self.language,
                    "-s", str(self.speed),
                    text,
                ],
                capture_output=True,
                timeout=60,
            )
            return True
        except Exception:
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return self._cmd or "espeak"
