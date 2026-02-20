"""STT engine using NVIDIA Parakeet via onnx-asr (ONNX runtime, no PyTorch)."""

from __future__ import annotations

import importlib
import logging
import os
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from voxtype.stt.base import STTEngine, STTResult
from voxtype.stt.faster_whisper import _filter_repetitions

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

# onnx-asr model identifiers for Parakeet
# Multilingual Parakeet V3: 25 European languages, auto language detection
# ~670 MB ONNX weights downloaded from HuggingFace on first use
PARAKEET_MODELS: dict[str, str] = {
    "parakeet-v3": "nemo-parakeet-tdt-0.6b-v3",
}

_INSTALL_PACKAGE = "onnx-asr"
_INSTALL_EXTRA = "parakeet"  # pip install 'voxtype[parakeet]'

def is_parakeet_model(model_size: str) -> bool:
    """Return True if *model_size* should use the Parakeet engine."""
    return model_size.startswith("parakeet")

def _is_onnx_asr_installed() -> bool:
    """Check if onnx-asr is importable."""
    try:
        import onnx_asr  # noqa: F401

        return True
    except ImportError:
        return False

def _install_onnx_asr(console=None) -> None:
    """Install onnx-asr with user confirmation.

    Args:
        console: Rich Console for interactive prompts. If None, uses plain input().

    Raises:
        RuntimeError: If user declines or install fails.
    """
    pkg_info = f"[bold]{_INSTALL_PACKAGE}[/bold] (~122 kB + ~670 MB model weights)"

    if console:
        from rich.prompt import Confirm

        console.print()
        console.print(f"[yellow]Parakeet V3 requires {pkg_info}[/]")
        console.print("[dim]ONNX runtime — no PyTorch required[/]")
        console.print()

        confirmed = Confirm.ask("Install now?", default=True, console=console)
    else:
        print(f"\nParakeet V3 requires {_INSTALL_PACKAGE} (~122 kB + ~670 MB model).")
        answer = input("Install now? [Y/n] ").strip().lower()
        confirmed = answer in ("", "y", "yes")

    if not confirmed:
        raise RuntimeError(
            f"Parakeet requires {_INSTALL_PACKAGE}.\n"
            f"Install with:  pip install 'voxtype[{_INSTALL_EXTRA}]'"
        )

    if console:
        console.print()

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", _INSTALL_PACKAGE],
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Install failed.\n"
            f"Try manually:  pip install 'voxtype[{_INSTALL_EXTRA}]'"
        )

    # Make newly installed package importable in the current process
    importlib.invalidate_caches()

    if console:
        console.print()
        console.print(f"[green]✓ {_INSTALL_PACKAGE} installed[/]")
        console.print()

class ParakeetEngine(STTEngine):
    """STT engine using NVIDIA Parakeet via onnx-asr.

    Parakeet-TDT-0.6B-v3 supports 25 European languages (Italian, German,
    Spanish, French, …) with automatic language detection. Runs via ONNX
    runtime — no PyTorch required.

    The onnx-asr Python package (~122 kB) is installed on first use with user
    confirmation. Model weights (~670 MB) are downloaded from HuggingFace
    automatically on first transcription.

    Set in ``[stt]``::

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
        """Load the Parakeet model.

        If onnx-asr is not installed and a console is available, prompts the
        user to install it. In headless mode, raises RuntimeError with install
        instructions.

        Args:
            model_size: "parakeet-v3" (default, multilingual TDT 0.6B).
            console: Rich Console for interactive prompts and progress output.
            headless: If True, suppress interactive prompts (daemon mode).
            **kwargs: Ignored (accepted for API compatibility with other engines).

        Raises:
            RuntimeError: If onnx-asr is not installed (headless mode or user
                declined install), or if model download fails.
        """
        # Ensure onnx-asr is installed
        if not _is_onnx_asr_installed():
            if headless:
                raise RuntimeError(
                    f"Parakeet requires {_INSTALL_PACKAGE}.\n"
                    f"Run:  voxtype stt install {model_size}"
                )
            _install_onnx_asr(console=console)

        model_name = PARAKEET_MODELS.get(model_size, PARAKEET_MODELS["parakeet-v3"])

        if not headless and console:
            console.print(f"[cyan]Loading Parakeet model '{model_size}'...[/]")
            console.print(
                "[dim]Model weights (~670 MB) will be downloaded from HuggingFace "
                "on first use.[/]"
            )

        # Suppress onnx-asr / onnxruntime noise
        logging.getLogger("onnxruntime").setLevel(logging.WARNING)

        from onnx_asr import load_model as _load_model

        self._model = _load_model(model_name)
        self._model_size = model_size

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
        import soundfile as sf

        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # onnx-asr accepts file paths; write to a temporary WAV for safety
        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        try:
            os.close(fd)
            sf.write(tmp_path, audio, 16000)
            result = self._model.transcribe(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        # onnx-asr may return a string or an object with a .text attribute
        if isinstance(result, str):
            text = result
        elif hasattr(result, "text"):
            text = result.text
        else:
            text = str(result)

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
