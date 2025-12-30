"""Base TTS interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class TTSEngine(ABC):
    """Abstract text-to-speech interface."""

    @abstractmethod
    def speak(self, text: str) -> bool:
        """Speak text aloud.

        Args:
            text: Text to speak.

        Returns:
            True if successful.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if TTS engine is available."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get engine name."""
        pass
