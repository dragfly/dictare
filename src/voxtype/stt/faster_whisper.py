"""STT engine using faster-whisper."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from voxtype.stt.base import STTEngine

if TYPE_CHECKING:
    from numpy.typing import NDArray

    import numpy as np

# Model sizes and their Hugging Face repo names
_MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "tiny.en": "Systran/faster-whisper-tiny.en",
    "base": "Systran/faster-whisper-base",
    "base.en": "Systran/faster-whisper-base.en",
    "small": "Systran/faster-whisper-small",
    "small.en": "Systran/faster-whisper-small.en",
    "medium": "Systran/faster-whisper-medium",
    "medium.en": "Systran/faster-whisper-medium.en",
    "large-v1": "Systran/faster-whisper-large-v1",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "Systran/faster-whisper-large-v3-turbo",
}

# Approximate model sizes in MB for display
_MODEL_SIZES_MB = {
    "tiny": 75,
    "tiny.en": 75,
    "base": 145,
    "base.en": 145,
    "small": 465,
    "small.en": 465,
    "medium": 1500,
    "medium.en": 1500,
    "large-v1": 3000,
    "large-v2": 3000,
    "large-v3": 3000,
    "large-v3-turbo": 1600,
}

def _is_model_cached(model_size: str) -> bool:
    """Check if model is already downloaded."""
    try:
        from huggingface_hub import try_to_load_from_cache

        repo_id = _MODEL_REPOS.get(model_size, f"Systran/faster-whisper-{model_size}")
        # Check for the main model file
        result = try_to_load_from_cache(repo_id, "model.bin")
        return result is not None and os.path.exists(result)
    except Exception:
        return False

def _download_model_with_progress(model_size: str, console=None) -> str:
    """Download model with progress bar, return local path."""
    from huggingface_hub import snapshot_download
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )

    repo_id = _MODEL_REPOS.get(model_size, f"Systran/faster-whisper-{model_size}")
    size_mb = _MODEL_SIZES_MB.get(model_size, "?")

    if console:
        console.print(f"[cyan]Downloading model {model_size} (~{size_mb} MB)...[/]")

    # Download with rich progress bar
    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        # huggingface_hub handles its own progress, but we show a wrapper
        task = progress.add_task(f"Downloading {model_size}", total=None)

        local_path = snapshot_download(
            repo_id,
            local_files_only=False,
            token=False,  # Public repos don't need auth
        )

        progress.update(task, completed=True)

    if console:
        console.print(f"[green]Model downloaded to cache[/]")

    return local_path

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
        console=None,
        verbose: bool = False,
        **kwargs,
    ) -> None:
        """Load the Whisper model.

        Args:
            model_size: Model size (tiny/base/small/medium/large-v3).
            device: Device to use (cpu/cuda/auto).
            compute_type: Compute type (int8/float16/float32).
            console: Optional Rich console for messages.
            verbose: Show detailed loading info.
            **kwargs: Additional options passed to WhisperModel.
        """
        actual_device = device

        # Setup CUDA if requested (must happen BEFORE importing faster_whisper)
        if device == "cuda":
            from voxtype.cuda_setup import setup_cuda

            cuda_ok, actual_device = setup_cuda(console=console, verbose=verbose)
            if not cuda_ok and console:
                console.print("[yellow]Using CPU instead of GPU[/]")

        # Check if model needs downloading, show progress if so
        model_path = model_size  # Default: let faster-whisper handle it
        if not _is_model_cached(model_size):
            model_path = _download_model_with_progress(model_size, console)

        from faster_whisper import WhisperModel

        try:
            self._model = WhisperModel(
                model_path,
                device=actual_device,
                compute_type=compute_type,
                **kwargs,
            )
        except Exception as e:
            # If CUDA fails at runtime, fall back to CPU
            if actual_device == "cuda" and "cuda" in str(e).lower():
                if console:
                    console.print(f"[yellow]GPU error: {e}[/]")
                    console.print("[yellow]Falling back to CPU[/]")
                self._model = WhisperModel(
                    model_path,
                    device="cpu",
                    compute_type="int8",
                    **kwargs,
                )
                actual_device = "cpu"
            else:
                raise

        self._model_size = model_size
        self._device = actual_device

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
