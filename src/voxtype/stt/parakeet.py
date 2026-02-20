"""STT engine using NVIDIA Parakeet via NeMo ASR."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import TYPE_CHECKING

from voxtype.stt.base import STTEngine, STTResult
from voxtype.stt.faster_whisper import _filter_repetitions

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

# Model registry
PARAKEET_MODELS: dict[str, str] = {
    "parakeet-v3": "nvidia/parakeet-tdt-0.6b-v3",
    "parakeet-ctc": "nvidia/parakeet-ctc-1.1b",
}

# Approximate model sizes in MB for display
_MODEL_SIZES_MB: dict[str, int] = {
    "parakeet-v3": 2400,
    "parakeet-ctc": 4400,
}

def is_parakeet_model(model_size: str) -> bool:
    """Return True if *model_size* should use the Parakeet engine."""
    return model_size.startswith("parakeet")

class ParakeetEngine(STTEngine):
    """STT engine using NVIDIA Parakeet (NeMo ASR).

    Parakeet-TDT-0.6B-v3 is 10-20× faster than Whisper-large-v3-turbo on
    Apple Silicon while supporting 25 European languages (Italian, German,
    Spanish, French, …) with auto language detection.

    Install NeMo before use::

        pip install 'nemo_toolkit[asr]'

    Then set in ``[stt]``::

        model = "parakeet-v3"
    """

    def __init__(self) -> None:
        self._model = None
        self._model_size: str | None = None

    def load_model(
        self,
        model_size: str = "parakeet-v3",
        console=None,
        headless: bool = False,
        **kwargs,
    ) -> None:
        """Load the Parakeet model from Hugging Face via NeMo.

        Args:
            model_size: One of "parakeet-v3" (default) or "parakeet-ctc".
            console: Optional Rich console for progress messages.
            headless: If True, suppress all console output.
            **kwargs: Ignored (accepted for API compatibility with other engines).

        Raises:
            RuntimeError: If NeMo is not installed or model download fails.
        """
        try:
            import nemo.collections.asr as nemo_asr
        except ImportError as exc:
            raise RuntimeError(
                "Parakeet requires the NeMo ASR toolkit.\n"
                "Install with:  pip install 'nemo_toolkit[asr]'\n"
                "Note: NeMo is a large package (~2 GB with dependencies)."
            ) from exc

        model_name = PARAKEET_MODELS.get(model_size, PARAKEET_MODELS["parakeet-v3"])
        size_mb = _MODEL_SIZES_MB.get(model_size, 2400)

        if not headless and console:
            console.print(
                f"[cyan]Loading Parakeet model '{model_size}' (~{size_mb} MB)...[/]"
            )
            console.print(f"[dim]Source: huggingface.co/{model_name}[/]")

        # NeMo is very verbose — quiet it down
        for noisy in ("nemo_logger", "nemo", "pytorch_lightning", "lightning"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

        self._model = nemo_asr.models.ASRModel.from_pretrained(model_name)
        self._model_size = model_size

        if not headless and console:
            console.print("[green]✓ Parakeet model loaded[/]")

    def transcribe(
        self,
        audio: NDArray[np.float32],
        language: str = "auto",
        hotwords: str | None = None,
        beam_size: int = 5,
        max_repetitions: int = 5,
        task: str = "transcribe",
    ) -> STTResult:
        """Transcribe audio using Parakeet.

        Args:
            audio: Audio samples (float32, mono, 16 kHz).
            language: Ignored — Parakeet auto-detects language.
            hotwords: Ignored — not supported by NeMo.
            beam_size: Ignored — not configurable via basic NeMo API.
            max_repetitions: Max consecutive word repetitions before filtering.
            task: Ignored — Parakeet only transcribes (no translate mode).

        Returns:
            STTResult with transcribed text. Language is always None because
            NeMo does not expose language ID through the basic ``transcribe``
            interface.

        Raises:
            RuntimeError: If model is not loaded.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        import numpy as np
        import soundfile as sf

        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # NeMo expects file paths — write to a temporary WAV file
        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        try:
            os.close(fd)
            sf.write(tmp_path, audio, 16000)
            output = self._model.transcribe([tmp_path])
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        # TDT models return Hypothesis objects (.text); CTC returns plain strings
        text = ""
        if output:
            first = output[0]
            text = first.text if hasattr(first, "text") else str(first)

        text = text.strip()
        filtered = _filter_repetitions(text, max_repeats=max_repetitions)
        return STTResult(text=filtered, language=None)

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None

    @property
    def model_size(self) -> str | None:
        """Get loaded model size."""
        return self._model_size
