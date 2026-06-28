"""Smoke tests for the Apple Silicon `mlx` optional-extra constellation.

These run only where the `mlx` extra is installed (CI job "auto: test macOS +
mlx" on an arm64 runner). They are the real coverage the ubuntu/`.[dev]` CI
cannot give: they catch ABI breaks (e.g. numpy 2.x against torch 2.0.1) and
version skew in the mlx family before a dependency bump lands.

The whole module skips cleanly when mlx is not importable, so it is a no-op on
Linux and on a plain `.[dev]` dev environment.
"""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.mlx

# Skip the entire module unless the mlx stack is installed.
mlx_whisper = pytest.importorskip("mlx_whisper")


def test_mlx_stack_imports() -> None:
    """The frozen mlx set must import together.

    This is the cheap, high-value check: importing torch fails outright if the
    numpy ABI it was built against is gone (the exact failure a numpy 1.x -> 2.x
    bump would cause while torch stays pinned at 2.0.1).
    """
    import mlx.core  # noqa: F401
    import mlx_audio  # noqa: F401
    import mlx_lm  # noqa: F401
    import numba  # noqa: F401
    import scipy  # noqa: F401
    import torch  # noqa: F401


def test_mlx_whisper_transcribes() -> None:
    """End-to-end: whisper-tiny loads and runs on real audio without crashing.

    Passes a float32 array straight in — the way the engine feeds mic frames —
    which exercises the mlx runtime without needing ffmpeg to decode a file.
    Asserts only the structural shape of the result, not transcription accuracy.
    """
    sr = 16000
    t = np.linspace(0, 2.0, sr * 2, endpoint=False)
    audio = (0.01 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

    result = mlx_whisper.transcribe(
        audio, path_or_hf_repo="mlx-community/whisper-tiny"
    )
    assert isinstance(result.get("text"), str)
