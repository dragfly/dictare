"""Contract tests for onnx-asr library API assumptions.

These tests verify our assumptions about the onnx-asr API by inspecting the
real library (no model weights downloaded). They catch the class of bug where
our mocks silently accepted wrong method names that don't exist at runtime.

Regressions caught:
- b165: we called .transcribe() — correct API is .recognize()
- b164: CoreML crashed with external ONNX data — must pass providers=["CPUExecutionProvider"]
"""

from __future__ import annotations

import inspect

from onnx_asr import load_model
from onnx_asr.adapters import TextResultsAsrAdapter

class TestTextResultsAsrAdapterContract:
    """Verify the API surface of the object returned by load_model()."""

    def test_has_recognize_not_transcribe(self):
        """Regression b165: .transcribe() doesn't exist — correct method is .recognize()."""
        assert callable(getattr(TextResultsAsrAdapter, "recognize", None))
        assert not hasattr(TextResultsAsrAdapter, "transcribe")

    def test_recognize_accepts_sample_rate_kwarg(self):
        """We call .recognize(audio, sample_rate=16_000) — param must exist."""
        sig = inspect.signature(TextResultsAsrAdapter.recognize)
        assert "sample_rate" in sig.parameters

    def test_recognize_first_positional_is_waveform(self):
        """First arg after self must accept a numpy array (waveform)."""
        sig = inspect.signature(TextResultsAsrAdapter.recognize)
        params = [p for p in sig.parameters if p != "self"]
        assert params[0] == "waveform"

class TestLoadModelContract:
    """Verify the load_model() function API."""

    def test_return_type_is_text_results_adapter(self):
        """load_model() must return TextResultsAsrAdapter, not some other adapter."""
        sig = inspect.signature(load_model)
        assert sig.return_annotation is TextResultsAsrAdapter

    def test_accepts_providers_kwarg(self):
        """Regression b164: must be able to pass providers=["CPUExecutionProvider"]
        to prevent CoreMLExecutionProvider from crashing on external ONNX data files."""
        sig = inspect.signature(load_model)
        assert "providers" in sig.parameters
