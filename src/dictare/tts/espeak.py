"""eSpeak TTS backend."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from dictare.tts.base import TTSEngine

logger = logging.getLogger(__name__)


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
        """Detect espeak or espeak-ng (stores full path for daemon safety)."""
        path = shutil.which("espeak-ng")
        if path:
            return path
        path = shutil.which("espeak")
        if path:
            return path
        # Fallback: launchd services don't inherit Homebrew PATH
        for fallback in ("/opt/homebrew/bin/espeak-ng", "/usr/local/bin/espeak-ng"):
            if Path(fallback).exists():
                return fallback
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
            logger.warning("espeak: no binary found")
            return False

        try:
            result = subprocess.run(
                [
                    self._cmd,
                    "-v", self.language,
                    "-s", str(self.speed),
                    text,
                ],
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning(
                    "espeak exited %d: %s",
                    result.returncode,
                    result.stderr.decode(errors="replace").strip(),
                )
                return False
            return True
        except Exception:
            logger.warning("espeak subprocess failed", exc_info=True)
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return self._cmd or "espeak"
