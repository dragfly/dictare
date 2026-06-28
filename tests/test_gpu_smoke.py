"""GPU smoke tests for the Linux/CUDA `gpu` extra (ctranslate2 / faster-whisper).

Real coverage for the `gpu` optional-extra. CI installs only `.[dev]`, so the
CUDA path (nvidia-cudnn-cu12 against ctranslate2's cuDNN ABI) is never tested
there. Run where an NVIDIA GPU + the extra exist — the same shape as every
other CI job:

    pip install -e ".[dev,gpu]" && pytest -m gpu

Skips cleanly when ctranslate2/faster-whisper are absent or no CUDA device is
present, so it is a no-op on Linux-without-gpu, macOS, and plain `.[dev]`.
"""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.gpu

# Skip unless the gpu stack is installed.
ctranslate2 = pytest.importorskip("ctranslate2")
faster_whisper = pytest.importorskip("faster_whisper")


def _cuda_devices() -> int:
    try:
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def test_cuda_device_present() -> None:
    """ctranslate2 must see at least one CUDA device."""
    if _cuda_devices() < 1:
        pytest.skip("no CUDA device available")
    assert _cuda_devices() >= 1


def test_faster_whisper_cuda_transcribes() -> None:
    """End-to-end: load whisper-tiny on CUDA and transcribe.

    This is where the cuDNN / ctranslate2 ABI actually runs — the real check
    that the installed nvidia-cudnn-cu12 is compatible with ctranslate2.
    """
    if _cuda_devices() < 1:
        pytest.skip("no CUDA device available")

    model = faster_whisper.WhisperModel("tiny", device="cuda", compute_type="float16")

    sr = 16000
    t = np.linspace(0, 2.0, sr * 2, endpoint=False)
    audio = (0.01 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

    segments, _info = model.transcribe(audio)
    # Force generator evaluation — inference (and thus the cuDNN kernels) runs here.
    text = "".join(seg.text for seg in segments)
    assert isinstance(text, str)
