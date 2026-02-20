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
    def _make_engine(self, transcribe_result="hello world"):
        """Return a ParakeetEngine with a pre-loaded mock model."""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = transcribe_result
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
        engine, _ = self._make_engine("ciao mondo")
        audio = np.zeros(16000, dtype=np.float32)
        with patch("soundfile.write"), \
             patch("os.unlink"), \
             patch("tempfile.mkstemp", return_value=(0, "/tmp/t.wav")), \
             patch("os.close"):
            result = engine.transcribe(audio)
        assert result.text == "ciao mondo"

    # --- transcribe: object with .text ---

    def test_transcribe_hypothesis_object(self):
        hyp = MagicMock()
        hyp.text = "buongiorno"
        engine, _ = self._make_engine(hyp)
        audio = np.zeros(16000, dtype=np.float32)
        with patch("soundfile.write"), \
             patch("os.unlink"), \
             patch("tempfile.mkstemp", return_value=(0, "/tmp/t.wav")), \
             patch("os.close"):
            result = engine.transcribe(audio)
        assert result.text == "buongiorno"

    # --- transcribe: edge cases ---

    def test_transcribe_raises_if_not_loaded(self):
        engine = ParakeetEngine()
        with pytest.raises(RuntimeError, match="not loaded"):
            engine.transcribe(np.zeros(16000, dtype=np.float32))

    def test_transcribe_converts_int16_to_float32(self):
        engine, _ = self._make_engine("test")
        audio = np.zeros(16000, dtype=np.int16)
        with patch("soundfile.write") as mock_write, \
             patch("os.unlink"), \
             patch("tempfile.mkstemp", return_value=(0, "/tmp/t.wav")), \
             patch("os.close"):
            engine.transcribe(audio)
            written_audio = mock_write.call_args[0][1]
            assert written_audio.dtype == np.float32

    def test_transcribe_cleans_up_tempfile(self):
        engine, _ = self._make_engine("text")
        audio = np.zeros(16000, dtype=np.float32)
        with patch("soundfile.write"), \
             patch("os.unlink") as mock_unlink, \
             patch("tempfile.mkstemp", return_value=(0, "/tmp/t.wav")), \
             patch("os.close"):
            engine.transcribe(audio)
            mock_unlink.assert_called_once_with("/tmp/t.wav")

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

    def test_load_model_uses_cpu_provider(self):
        """CoreML fails with ONNX external data; must force CPUExecutionProvider."""
        engine = ParakeetEngine()
        mock_load = MagicMock(return_value=MagicMock())
        with patch.dict("sys.modules", {"onnx_asr": MagicMock(load_model=mock_load)}):
            engine.load_model("parakeet-v3", headless=True)
        mock_load.assert_called_once_with(
            "nemo-parakeet-tdt-0.6b-v3", providers=["CPUExecutionProvider"]
        )
