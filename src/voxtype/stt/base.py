"""Abstract base class for STT engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


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
        hotwords: str | None = None,
        beam_size: int = 5,
        max_repetitions: int = 5,
    ) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio samples (float32, mono, 16kHz).
            language: Language code or "auto" for auto-detection.
            hotwords: Comma-separated words to boost recognition.
                Note: Optional, may be ignored by some engines (e.g., MLX).
            beam_size: Beam size for decoding (higher = more accurate, slower).
                Note: Optional, may be ignored by some engines (e.g., MLX).
            max_repetitions: Max consecutive word repetitions before filtering.

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
