"""STT engine using faster-whisper."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from voxtype.stt.base import STTEngine

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

# Model sizes and their Hugging Face repo names
# Note: turbo models use None - handled natively by faster-whisper
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
    "turbo": None,
    "large-v3-turbo": None,
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
    import logging

    repo_id = _MODEL_REPOS.get(model_size)
    if repo_id is None:
        # Turbo models: check faster-whisper's cache location
        return _is_turbo_model_cached()

    try:
        from huggingface_hub import try_to_load_from_cache

        # Check for the main model file
        result = try_to_load_from_cache(repo_id, "model.bin")
        return result is not None and os.path.exists(result)
    except Exception as e:
        logging.getLogger(__name__).debug(f"Error checking model cache for {model_size}: {e}")
        return False

def _is_turbo_model_cached() -> bool:
    """Check if turbo model is cached (faster-whisper uses mobiuslabsgmbh repo)."""
    import logging

    try:
        from huggingface_hub import try_to_load_from_cache

        # faster-whisper uses this repo for turbo
        result = try_to_load_from_cache(
            "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "model.bin"
        )
        return result is not None and os.path.exists(result)
    except Exception as e:
        logging.getLogger(__name__).debug(f"Error checking turbo model cache: {e}")
        return False

def _download_model_with_progress(model_size: str, console=None) -> str:
    """Download model with real progress bar (monitors cache size), return local path."""
    import os as _os

    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import (
        HfHubHTTPError,
        RepositoryNotFoundError,
    )

    from voxtype.utils.hf_download import (
        DownloadProgressMonitor,
        get_repo_size,
        is_repo_cached,
    )

    repo_id = _MODEL_REPOS.get(model_size)
    if repo_id is None:
        return model_size  # Turbo models: let faster-whisper handle

    # Check if already cached
    if is_repo_cached(repo_id, "model.bin"):
        return snapshot_download(repo_id, local_files_only=True)

    # Get expected size from API (or use fallback)
    expected_size = get_repo_size(repo_id)
    fallback_mb = _MODEL_SIZES_MB.get(model_size, 500)
    if expected_size is None:
        expected_size = fallback_mb * 1024 * 1024

    if console:
        console.print(f"[cyan]Downloading Whisper model '{model_size}' ({expected_size / 1e6:.0f} MB)...[/]")
        console.print(f"[dim]Source: huggingface.co/{repo_id}[/]")

    # Clear any HF credentials from environment to avoid auth issues with public repos
    hf_env_vars = ["HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HF_HUB_TOKEN"]
    saved_env = {}
    for var in hf_env_vars:
        if var in _os.environ:
            saved_env[var] = _os.environ.pop(var)

    try:
        from rich.progress import (
            BarColumn,
            DownloadColumn,
            Progress,
            TextColumn,
            TimeRemainingColumn,
            TransferSpeedColumn,
        )

        # Real progress bar with cache monitoring
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Downloading {model_size}", total=expected_size)

            with DownloadProgressMonitor(repo_id, expected_size, progress, task):
                local_path = snapshot_download(
                    repo_id,
                    local_files_only=False,
                    token=False,  # Public repos - no auth needed
                )

        if console:
            console.print("[green]✓ Model downloaded successfully[/]")

        return local_path

    except RepositoryNotFoundError as e:
        if console:
            console.print("\n[red bold]Download failed: Model not found[/]")
            console.print(f"[yellow]Repository: {repo_id}[/]")
            if "401" in str(e) or "Unauthorized" in str(e):
                console.print("\n[yellow]Authentication error - invalid cached credentials.[/]")
                console.print("[dim]The Whisper models are public and don't require login.[/]")
                console.print("[dim]Remove cached/invalid credentials:[/]")
                console.print("[cyan]  rm -f ~/.cache/huggingface/token ~/.huggingface/token[/]")
                console.print("[dim]Also check ~/.netrc for huggingface.co entries[/]")
            else:
                console.print(f"\n[dim]Error: {e}[/]")
        raise RuntimeError(f"Model '{model_size}' not found on Hugging Face") from e

    except HfHubHTTPError as e:
        if console:
            console.print("\n[red bold]Download failed: Network error[/]")
            if "401" in str(e) or "Unauthorized" in str(e):
                console.print("\n[yellow]Authentication error - invalid cached credentials.[/]")
                console.print("[dim]The Whisper models are public and don't require login.[/]")
                console.print("[dim]Remove cached/invalid credentials:[/]")
                console.print("[cyan]  rm -f ~/.cache/huggingface/token ~/.huggingface/token[/]")
                console.print("[dim]Also check ~/.netrc for huggingface.co entries[/]")
            elif "403" in str(e):
                console.print("\n[yellow]Access denied. The model may require acceptance of terms.[/]")
                console.print(f"[dim]Visit: https://huggingface.co/{repo_id}[/]")
            else:
                console.print(f"\n[dim]Error: {e}[/]")
        raise RuntimeError(f"Failed to download model '{model_size}'") from e

    except Exception as e:
        if console:
            console.print("\n[red bold]Download failed[/]")
            console.print(f"[dim]Error: {e}[/]")
            console.print("\n[yellow]Troubleshooting:[/]")
            console.print("[dim]1. Check your internet connection[/]")
            console.print("[dim]2. Try again in a few minutes (Hugging Face may be busy)[/]")
            console.print("[dim]3. Clear HF cache: rm -rf ~/.cache/huggingface/hub/models--Systran--*[/]")
        raise RuntimeError(f"Failed to download model '{model_size}'") from e

    finally:
        # Restore environment variables
        for var, value in saved_env.items():
            _os.environ[var] = value

def _filter_repetitions(text: str, max_repeats: int = 5) -> str:
    """Filter out hallucinated repetitions (e.g., 'la la la la la la...').

    Whisper can hallucinate repetitive patterns when there's background noise
    or silence. This filter removes excessive consecutive repetitions.

    Args:
        text: Transcribed text to filter.
        max_repeats: Maximum allowed consecutive repetitions of a word.

    Returns:
        Filtered text with repetitions truncated.
    """
    words = text.split()
    if len(words) < max_repeats:
        return text

    result = []
    repeat_count = 1
    for i, word in enumerate(words):
        if i > 0 and word.lower() == words[i - 1].lower():
            repeat_count += 1
            if repeat_count > max_repeats:
                continue  # Skip excessive repetitions
        else:
            repeat_count = 1
        result.append(word)

    return " ".join(result)

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
        headless: bool = False,
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
        actual_compute_type = compute_type

        # Setup CUDA if requested (must happen BEFORE importing faster_whisper)
        if device == "cuda":
            from voxtype.cuda_setup import setup_cuda

            cuda_ok, actual_device = setup_cuda(console=console, verbose=verbose)
            if not cuda_ok:
                # CPU doesn't support float16, use int8
                actual_compute_type = "int8"
                if console:
                    console.print("[yellow]Using CPU instead of GPU[/]")

        # Check if model needs downloading, show progress if so
        model_path = model_size  # Default: let faster-whisper handle it
        needs_download = not _is_model_cached(model_size)

        if needs_download:
            if _MODEL_REPOS.get(model_size) is None:
                # Turbo models: faster-whisper handles download, just show message
                size_mb = _MODEL_SIZES_MB.get(model_size, "?")
                if console:
                    console.print(
                        f"[cyan]Downloading Whisper model '{model_size}' (~{size_mb} MB)...[/]"
                    )
                    console.print("[dim]This may take a few minutes...[/]")
            else:
                # Other models: use our progress bar
                model_path = _download_model_with_progress(model_size, console)

        # Suppress HF "unauthenticated requests" warning (not useful for users)
        import logging
        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

        from faster_whisper import WhisperModel

        try:
            self._model = WhisperModel(
                model_path,
                device=actual_device,
                compute_type=actual_compute_type,
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
        hotwords: str | None = None,
        beam_size: int = 5,
        max_repetitions: int = 5,
        task: str = "transcribe",
    ) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio samples (float32, mono, 16kHz).
            language: Language code or "auto" for auto-detection.
            hotwords: Comma-separated words to boost recognition.
            beam_size: Beam size for decoding.
            max_repetitions: Max consecutive word repetitions before filtering.
            task: "transcribe" for same-language output, "translate" for English output.

        Returns:
            Transcribed (or translated) text.

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

        # Build transcribe kwargs
        transcribe_kwargs = dict(
            language=lang,
            beam_size=beam_size,
            task=task,  # "transcribe" or "translate"
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        # Add hotwords if provided
        if hotwords:
            transcribe_kwargs["hotwords"] = hotwords

        # Transcribe with built-in VAD filtering
        segments, info = self._model.transcribe(audio, **transcribe_kwargs)

        # Collect all segment texts
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        text = " ".join(text_parts).strip()

        # Filter hallucinated repetitions (e.g., "la la la la la...")
        return _filter_repetitions(text, max_repeats=max_repetitions)

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None

    @property
    def model_size(self) -> str | None:
        """Get loaded model size."""
        return self._model_size
