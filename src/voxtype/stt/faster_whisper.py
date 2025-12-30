"""STT engine using faster-whisper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from voxtype.stt.base import STTEngine

if TYPE_CHECKING:
    from numpy.typing import NDArray

    import numpy as np

class FasterWhisperEngine(STTEngine):
    """STT engine using faster-whisper (CTranslate2-based)."""

    def __init__(self) -> None:
        """Initialize faster-whisper engine."""
        self._model = None
        self._model_size: str | None = None

    def load_model(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        **kwargs,
    ) -> None:
        """Load the Whisper model.

        Args:
            model_size: Model size (tiny/base/small/medium/large-v3).
            device: Device to use (cpu/cuda).
            compute_type: Compute type (int8/float16/float32).
            **kwargs: Additional options passed to WhisperModel.
        """
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            **kwargs,
        )
        self._model_size = model_size

    def transcribe(
        self,
        audio: NDArray[np.float32],
        language: str = "auto",
        beam_size: int = 5,
    ) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio samples (float32, mono, 16kHz).
            language: Language code or "auto" for auto-detection.
            beam_size: Beam size for decoding.

        Returns:
            Transcribed text.

        Raises:
            RuntimeError: If model is not loaded.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        import numpy as np

        # Ensure float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Handle language
        lang = None if language == "auto" else language

        # Transcribe with built-in VAD filtering
        segments, info = self._model.transcribe(
            audio,
            language=lang,
            beam_size=beam_size,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        # Collect all segment texts
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        return " ".join(text_parts).strip()

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None

    @property
    def model_size(self) -> str | None:
        """Get loaded model size."""
        return self._model_size
