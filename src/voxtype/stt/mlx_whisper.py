"""STT engine using mlx-whisper for Apple Silicon."""

from __future__ import annotations

from typing import TYPE_CHECKING

from voxtype.stt.base import STTEngine

if TYPE_CHECKING:
    from numpy.typing import NDArray

    import numpy as np


# Model mapping for mlx-community hub
MLX_MODELS = {
    "tiny": "mlx-community/whisper-tiny",
    "base": "mlx-community/whisper-base",
    "small": "mlx-community/whisper-small",
    "medium": "mlx-community/whisper-medium",
    "large": "mlx-community/whisper-large-v3",
    "large-v3": "mlx-community/whisper-large-v3",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


class MLXWhisperEngine(STTEngine):
    """STT engine using mlx-whisper for Apple Silicon acceleration."""

    def __init__(self) -> None:
        """Initialize mlx-whisper engine."""
        self._model_path: str | None = None
        self._model_size: str | None = None

    def load_model(
        self,
        model_size: str = "base",
        **kwargs,
    ) -> None:
        """Load the Whisper model.

        Args:
            model_size: Model size (tiny/base/small/medium/large-v3).
            **kwargs: Additional options (ignored for MLX).
        """
        self._model_path = MLX_MODELS.get(model_size, f"mlx-community/whisper-{model_size}")
        self._model_size = model_size

        # Pre-load the model now (downloads if needed)
        # Use ModelHolder so the model is cached and reused by transcribe()
        # Default is fp16=True, so use float16 to match transcribe()
        import mlx.core as mx
        from mlx_whisper.transcribe import ModelHolder
        ModelHolder.get_model(self._model_path, mx.float16)

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

        Raises:
            RuntimeError: If model is not loaded.
        """
        if self._model_path is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        import mlx_whisper
        import numpy as np

        # Ensure float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Handle language
        lang = None if language == "auto" else language

        # Transcribe using mlx-whisper
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self._model_path,
            language=lang,
        )

        # Extract text from result
        text = result.get("text", "")
        return text.strip()

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model_path is not None

    @property
    def model_size(self) -> str | None:
        """Get loaded model size."""
        return self._model_size
