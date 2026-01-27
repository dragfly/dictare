"""macOS 'say' TTS backend."""

from __future__ import annotations

import shutil
import subprocess
import sys

from voxtype.tts.base import TTSEngine

class SayTTS(TTSEngine):
    """TTS using macOS built-in 'say' command."""

    def __init__(self, language: str = "en", speed: int = 175, voice: str = "") -> None:
        """Initialize macOS say TTS.

        Args:
            language: Language code (used to select appropriate voice if voice is empty).
            speed: Speech rate in words per minute (90-720, default 175).
            voice: Voice name (e.g., 'Samantha', 'Daniel'). Empty = system default.
        """
        self.language = language
        self.speed = max(90, min(720, speed))  # Clamp to valid range
        self.voice = voice

    def is_available(self) -> bool:
        """Check if say is available (macOS only)."""
        return sys.platform == "darwin" and shutil.which("say") is not None

    def speak(self, text: str) -> bool:
        """Speak text using macOS say.

        Args:
            text: Text to speak.

        Returns:
            True if successful.
        """
        if not self.is_available():
            return False

        try:
            cmd = ["say", "-r", str(self.speed)]
            if self.voice:
                cmd.extend(["-v", self.voice])
            cmd.append(text)

            subprocess.run(cmd, capture_output=True, timeout=120)
            return True
        except Exception:
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return "say"
