"""Voice Activity Detection interface (stub for future implementation)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from numpy.typing import NDArray

    import numpy as np


class VADEngine(ABC):
    """Abstract Voice Activity Detection interface.

    This is a stub for future Silero VAD integration.
    """

    @abstractmethod
    def is_speech(self, audio_chunk: NDArray[np.float32]) -> bool:
        """Check if audio chunk contains speech.

        Args:
            audio_chunk: Audio samples (float32, mono, 16kHz).

        Returns:
            True if speech is detected.
        """
        pass

    @abstractmethod
    def process_stream(
        self,
        on_speech_start: Callable[[], None],
        on_speech_end: Callable[[NDArray[np.float32]], None],
    ) -> None:
        """Process audio stream and call callbacks on speech events.

        Args:
            on_speech_start: Called when speech starts.
            on_speech_end: Called when speech ends, with accumulated audio.
        """
        pass


class NoVAD(VADEngine):
    """Dummy VAD that always returns True (no filtering)."""

    def is_speech(self, audio_chunk: NDArray[np.float32]) -> bool:
        """Always returns True (no VAD filtering)."""
        return True

    def process_stream(
        self,
        on_speech_start: Callable[[], None],
        on_speech_end: Callable[[NDArray[np.float32]], None],
    ) -> None:
        """Not implemented for NoVAD."""
        raise NotImplementedError("NoVAD does not support stream processing")


# Future implementation:
# class SileroVAD(VADEngine):
#     """Silero VAD implementation."""
#
#     def __init__(self, threshold: float = 0.5):
#         self.threshold = threshold
#         self._model = None
#
#     def load_model(self):
#         import torch
#         self._model, utils = torch.hub.load(
#             repo_or_dir='snakers4/silero-vad',
#             model='silero_vad',
#             force_reload=False
#         )
#
#     def is_speech(self, audio_chunk) -> bool:
#         import torch
#         audio_tensor = torch.from_numpy(audio_chunk)
#         speech_prob = self._model(audio_tensor, 16000).item()
#         return speech_prob > self.threshold
