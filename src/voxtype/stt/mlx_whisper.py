"""STT engine using mlx-whisper for Apple Silicon."""

from __future__ import annotations

from typing import TYPE_CHECKING

from voxtype.stt.base import STTEngine, STTResult
from voxtype.stt.faster_whisper import _filter_repetitions

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


# Model mapping for mlx-community hub
MLX_MODELS = {
    "tiny": "mlx-community/whisper-tiny",
    "base": "mlx-community/whisper-base",
    "small": "mlx-community/whisper-small",
    "medium": "mlx-community/whisper-medium",
    "large": "mlx-community/whisper-large-v3-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
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
        *,
        headless: bool = False,
        **kwargs,
    ) -> None:
        """Load the Whisper model.

        Args:
            model_size: Model size (tiny/base/small/medium/large-v3).
            headless: If True, skip all console output (for Engine/daemon mode).
            **kwargs: Additional options (ignored for MLX).
        """
        self._model_path = MLX_MODELS.get(model_size, f"mlx-community/whisper-{model_size}")
        self._model_size = model_size

        # Define load function that includes imports (they can be slow)
        model_path = self._model_path  # Capture for closure

        def load_model_fn():
            import mlx.core as mx
            from mlx_whisper.transcribe import ModelHolder

            return ModelHolder.get_model(model_path, mx.float16)

        # Check if model is already cached
        if self._is_model_cached(self._model_path):
            # Model cached - load with progress indicator (headless skips UI)
            from voxtype.utils.loading import load_with_indicator

            load_with_indicator(
                self._model_path,
                "STT model",
                load_model_fn,
                headless=headless,
            )
        else:
            # Model not cached - download with nice Rich progress bar
            # Note: download cannot be headless (user needs to see download progress)
            from voxtype.utils.hf_download import download_with_progress

            download_with_progress(
                self._model_path,
                load_model_fn,
                fallback_size_gb=3.0,  # Large-v3-turbo is ~3GB
            )

    def _is_model_cached(self, repo_id: str) -> bool:
        """Check if a HuggingFace model is already cached.

        Args:
            repo_id: HuggingFace repo ID (e.g., "mlx-community/whisper-large-v3-turbo")

        Returns:
            True if model files are cached locally.
        """
        import logging

        try:
            from huggingface_hub import try_to_load_from_cache
            # Check if the config file is cached (good indicator the model is downloaded)
            result = try_to_load_from_cache(repo_id, "config.json")
            return result is not None
        except Exception as e:
            logging.getLogger(__name__).debug(f"Error checking model cache for {repo_id}: {e}")
            return False

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
            hotwords: Comma-separated words to boost recognition (not supported by MLX).
            beam_size: Beam size for decoding (not supported by MLX).
            max_repetitions: Max consecutive word repetitions before filtering.
            task: "transcribe" for same-language output, "translate" for English output.

        Returns:
            STTResult with transcribed text and detected language.

        Raises:
            RuntimeError: If model is not loaded.
        """
        if self._model_path is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        # Note: hotwords and beam_size are ignored by MLX Whisper (not supported)
        _ = hotwords, beam_size

        import mlx_whisper
        import numpy as np

        # Ensure float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Handle language
        lang = None if language == "auto" else language

        # Transcribe using mlx-whisper
        # Note: When task=translate, don't force language - let Whisper detect it
        # Otherwise translation might be ignored
        effective_lang = None if task == "translate" else lang
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self._model_path,
            language=effective_lang,
            task=task,  # "transcribe" or "translate"
        )

        # Extract text from result
        text = result.get("text", "").strip()

        # Filter hallucinated repetitions (e.g., "la la la la la...")
        filtered_text = _filter_repetitions(text, max_repeats=max_repetitions)

        return STTResult(
            text=filtered_text,
            language=result.get("language"),
        )

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model_path is not None

    @property
    def model_size(self) -> str | None:
        """Get loaded model size."""
        return self._model_size
