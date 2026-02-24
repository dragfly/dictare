"""Abstract base class for STT engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

@dataclass
class STTResult:
    """Result of STT transcription."""

    text: str
    language: str | None = None
    language_confidence: float | None = None

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
        task: str = "transcribe",
    ) -> STTResult:
        """Transcribe audio to text.

        Args:
            audio: Audio samples (float32, mono, 16kHz).
            language: Language code or "auto" for auto-detection.
            hotwords: Comma-separated words to boost recognition.
                Note: Optional, may be ignored by some engines (e.g., MLX).
            beam_size: Beam size for decoding (higher = more accurate, slower).
                Note: Optional, may be ignored by some engines (e.g., MLX).
            max_repetitions: Max consecutive word repetitions before filtering.
            task: "transcribe" for same-language output, "translate" for English output.

        Returns:
            STTResult with transcribed text and detected language.
        """
        pass

    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if model is loaded.

        Returns:
            True if model is ready for transcription.
        """
        pass
