"""Tests for ParakeetEngine (onnx-asr backend)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voxtype.stt.parakeet import ParakeetEngine, is_parakeet_model


class TestIsParakeetModel:
    def test_parakeet_v3(self):
        assert is_parakeet_model("parakeet-v3") is True

    def test_parakeet_prefix(self):
        assert is_parakeet_model("parakeet-anything") is True

    def test_whisper_is_not_parakeet(self):
        assert is_parakeet_model("large-v3-turbo") is False

    def test_tiny_is_not_parakeet(self):
        assert is_parakeet_model("tiny") is False


class TestParakeetEngine:
    def _make_engine(self, recognize_result="hello world"):
        """Return a ParakeetEngine with a pre-loaded mock model."""
        mock_model = MagicMock()
        mock_model.recognize.return_value = recognize_result
        engine = ParakeetEngine()
        engine._model = mock_model
        engine._model_size = "parakeet-v3"
        return engine, mock_model

    # --- state ---

    def test_is_loaded_false_initially(self):
        assert ParakeetEngine().is_loaded() is False

    def test_is_loaded_true_after_model_set(self):
        engine, _ = self._make_engine()
        assert engine.is_loaded() is True

    def test_model_size_property(self):
        engine, _ = self._make_engine()
        assert engine.model_size == "parakeet-v3"

    # --- transcribe: string result ---

    def test_transcribe_string_result(self):
        engine, mock_model = self._make_engine("ciao mondo")
        audio = np.zeros(16000, dtype=np.float32)
        result = engine.transcribe(audio)
        assert result.text == "ciao mondo"
        mock_model.recognize.assert_called_once_with(audio, sample_rate=16_000)

    # --- transcribe: edge cases ---

    def test_transcribe_raises_if_not_loaded(self):
        engine = ParakeetEngine()
        with pytest.raises(RuntimeError, match="not loaded"):
            engine.transcribe(np.zeros(16000, dtype=np.float32))

    def test_transcribe_converts_int16_to_float32(self):
        engine, mock_model = self._make_engine("test")
        audio = np.zeros(16000, dtype=np.int16)
        engine.transcribe(audio)
        called_audio = mock_model.recognize.call_args[0][0]
        assert called_audio.dtype == np.float32

    # --- load_model ---

    def test_load_model_sets_model_size(self):
        engine = ParakeetEngine()
        mock_load = MagicMock(return_value=MagicMock())
        with patch.dict("sys.modules", {"onnx_asr": MagicMock(load_model=mock_load)}):
            engine.load_model("parakeet-v3", headless=True)
        assert engine._model_size == "parakeet-v3"
        assert engine.is_loaded()

    def test_load_model_sets_device_onnx(self):
        engine = ParakeetEngine()
        mock_load = MagicMock(return_value=MagicMock())
        with patch.dict("sys.modules", {"onnx_asr": MagicMock(load_model=mock_load)}):
            engine.load_model("parakeet-v3", headless=True)
        assert engine._device == "onnx"

    def test_load_model_forces_cpu_on_macos(self):
        """CoreML fails with ONNX external data files on macOS — must force CPUExecutionProvider."""
        engine = ParakeetEngine()
        mock_load = MagicMock(return_value=MagicMock())
        with patch.dict("sys.modules", {"onnx_asr": MagicMock(load_model=mock_load)}), \
             patch("sys.platform", "darwin"):
            engine.load_model("parakeet-v3", headless=True)
        mock_load.assert_called_once_with(
            "nemo-parakeet-tdt-0.6b-v3", providers=["CPUExecutionProvider"]
        )

    def test_load_model_auto_providers_on_linux(self):
        """On Linux, let onnxruntime pick providers (CUDA if available, CPU fallback)."""
        engine = ParakeetEngine()
        mock_load = MagicMock(return_value=MagicMock())
        with patch.dict("sys.modules", {"onnx_asr": MagicMock(load_model=mock_load)}), \
             patch("sys.platform", "linux"):
            engine.load_model("parakeet-v3", headless=True)
        mock_load.assert_called_once_with(
            "nemo-parakeet-tdt-0.6b-v3", providers=None
        )
