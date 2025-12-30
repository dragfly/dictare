"""Abstract base class for STT engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from numpy.typing import NDArray

    import numpy as np

class STTEngine(ABC):
    """Abstract base class for Speech-to-Text engines."""

    @abstractmethod
    def load_model(self, model_size: str, **kwargs) -> None:
        """Load the STT model.

        Args:
            model_size: Model size identifier (e.g., "tiny", "base", "small").
            **kwargs: Additional engine-specific options.
        """
        pass

    @abstractmethod
    def transcribe(
        self,
        audio: NDArray[np.float32],
        language: str = "auto",
    ) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio samples (float32, mono, 16kHz).
            language: Language code or "auto" for auto-detection.

        Returns:
            Transcribed text.
        """
        pass

    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if model is loaded.

        Returns:
            True if model is ready for transcription.
        """
        pass
