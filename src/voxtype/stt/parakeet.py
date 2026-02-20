"""STT engine using NVIDIA Parakeet via onnx-asr (ONNX runtime, no PyTorch).

Runtime stack:
  onnx-asr  →  onnxruntime  →  Parakeet ONNX weights (downloaded from HuggingFace)

onnxruntime (~15 MB) is lighter than ctranslate2 (~30 MB, used by faster-whisper)
and far lighter than PyTorch (~2 GB, used by the original NeMo/Whisper).
Model weights (~670 MB) are downloaded on first use.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from voxtype.stt.base import STTEngine, STTResult
from voxtype.stt.faster_whisper import _filter_repetitions

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

# onnx-asr model identifiers for Parakeet
# nemo-parakeet-tdt-0.6b-v3: 25 European languages, auto language detection
# Weights: ~670 MB (int8 quantized ONNX), downloaded from HuggingFace on first use
PARAKEET_MODELS: dict[str, str] = {
    "parakeet-v3": "nemo-parakeet-tdt-0.6b-v3",
}

def is_parakeet_model(model_size: str) -> bool:
    """Return True if *model_size* should use the Parakeet engine."""
    return model_size.startswith("parakeet")

class ParakeetEngine(STTEngine):
    """STT engine using NVIDIA Parakeet via onnx-asr.

    Parakeet-TDT-0.6B-v3 supports 25 European languages (Italian, German,
    Spanish, French, …) with automatic language detection. Runs via ONNX
    runtime — no PyTorch required.

    Model weights (~670 MB) are downloaded from HuggingFace automatically on
    first use (same pattern as faster-whisper).

    Set in ``[stt]``::

        model = "parakeet-v3"
    """

    def __init__(self) -> None:
        self._model: Any | None = None
        self._model_size: str | None = None
        self._device: str | None = None

    def load_model(
        self,
        model_size: str = "parakeet-v3",
        console=None,
        headless: bool = False,
        **kwargs,
    ) -> None:
        """Load the Parakeet model.

        Model weights (~670 MB) are downloaded from HuggingFace on first use.

        Args:
            model_size: "parakeet-v3" (default, multilingual TDT 0.6B).
            console: Rich Console for progress output.
            headless: If True, suppress console output (daemon mode).
            **kwargs: Ignored (accepted for API compatibility with other engines).
        """
        model_name = PARAKEET_MODELS.get(model_size, PARAKEET_MODELS["parakeet-v3"])

        if not headless and console:
            console.print(f"[cyan]Loading Parakeet model '{model_size}'...[/]")
            console.print(
                "[dim]Model weights (~670 MB) will be downloaded from HuggingFace "
                "on first use.[/]"
            )

        # Suppress onnxruntime noise
        logging.getLogger("onnxruntime").setLevel(logging.WARNING)

        import sys

        from onnx_asr import load_model as _load_model

        # On macOS, CoreMLExecutionProvider crashes with ONNX external data files (.onnx.data).
        # NemoConformerTdt does not exclude CoreML unlike NemoConformerAED, so we must force CPU.
        # On Linux, let onnxruntime pick automatically (CUDA if available, CPU fallback).
        providers = ["CPUExecutionProvider"] if sys.platform == "darwin" else None
        self._model = _load_model(model_name, providers=providers)
        self._model_size = model_size
        self._device = "onnx"

        if not headless and console:
            console.print("[green]✓ Parakeet model ready[/]")

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
            language: Ignored — Parakeet V3 auto-detects language.
            hotwords: Ignored — not supported by onnx-asr.
            beam_size: Ignored — not configurable via onnx-asr.
            max_repetitions: Max consecutive word repetitions before filtering.
            task: Ignored — Parakeet only transcribes (no translate mode).

        Returns:
            STTResult with transcribed text. language is always None because
            onnx-asr does not expose language ID through its transcribe API.

        Raises:
            RuntimeError: If model is not loaded.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        import numpy as np

        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # TextResultsAsrAdapter.recognize() accepts 1D float32 numpy arrays directly.
        # Returns str — no temp file needed.
        text: str = self._model.recognize(audio, sample_rate=16_000)
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
