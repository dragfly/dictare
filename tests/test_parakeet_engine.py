"""Tests for ParakeetEngine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voxtype.stt.parakeet import ParakeetEngine, is_parakeet_model

class TestIsParakeetModel:
    def test_parakeet_v3(self):
        assert is_parakeet_model("parakeet-v3") is True

    def test_parakeet_ctc(self):
        assert is_parakeet_model("parakeet-ctc") is True

    def test_parakeet_prefix(self):
        assert is_parakeet_model("parakeet-anything") is True

    def test_whisper_is_not_parakeet(self):
        assert is_parakeet_model("large-v3-turbo") is False

    def test_tiny_is_not_parakeet(self):
        assert is_parakeet_model("tiny") is False

class TestParakeetEngine:
    def _make_engine_with_mock_model(self, hypothesis_text: str = "hello world"):
        """Return a ParakeetEngine with a mocked NeMo model."""
        hypothesis = MagicMock()
        hypothesis.text = hypothesis_text

        mock_model = MagicMock()
        mock_model.transcribe.return_value = [hypothesis]

        engine = ParakeetEngine()
        engine._model = mock_model
        engine._model_size = "parakeet-v3"
        return engine, mock_model

    def test_is_loaded_false_initially(self):
        engine = ParakeetEngine()
        assert engine.is_loaded() is False

    def test_is_loaded_true_after_model_set(self):
        engine, _ = self._make_engine_with_mock_model()
        assert engine.is_loaded() is True

    def test_model_size_property(self):
        engine, _ = self._make_engine_with_mock_model()
        assert engine.model_size == "parakeet-v3"

    def test_transcribe_returns_text(self):
        engine, _ = self._make_engine_with_mock_model("ciao mondo")
        audio = np.zeros(16000, dtype=np.float32)

        with patch("soundfile.write"), patch("os.unlink"), patch("tempfile.mkstemp", return_value=(0, "/tmp/test.wav")), patch("os.close"):
            result = engine.transcribe(audio)

        assert result.text == "ciao mondo"

    def test_transcribe_raises_if_not_loaded(self):
        engine = ParakeetEngine()
        audio = np.zeros(16000, dtype=np.float32)
        with pytest.raises(RuntimeError, match="not loaded"):
            engine.transcribe(audio)

    def test_transcribe_converts_to_float32(self):
        engine, mock_model = self._make_engine_with_mock_model("test")
        audio = np.zeros(16000, dtype=np.int16)

        with patch("soundfile.write") as mock_write, patch("os.unlink"), patch("tempfile.mkstemp", return_value=(0, "/tmp/test.wav")), patch("os.close"):
            engine.transcribe(audio)
            written_audio = mock_write.call_args[0][1]
            assert written_audio.dtype == np.float32

    def test_transcribe_plain_string_output(self):
        """CTC models return plain strings instead of Hypothesis objects."""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ["plain string result"]

        engine = ParakeetEngine()
        engine._model = mock_model
        engine._model_size = "parakeet-ctc"

        audio = np.zeros(16000, dtype=np.float32)
        with patch("soundfile.write"), patch("os.unlink"), patch("tempfile.mkstemp", return_value=(0, "/tmp/test.wav")), patch("os.close"):
            result = engine.transcribe(audio)

        assert result.text == "plain string result"

    def test_transcribe_empty_output(self):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = []

        engine = ParakeetEngine()
        engine._model = mock_model

        audio = np.zeros(16000, dtype=np.float32)
        with patch("soundfile.write"), patch("os.unlink"), patch("tempfile.mkstemp", return_value=(0, "/tmp/test.wav")), patch("os.close"):
            result = engine.transcribe(audio)

        assert result.text == ""

    def test_load_model_raises_without_nemo(self):
        engine = ParakeetEngine()
        with patch.dict("sys.modules", {"nemo": None, "nemo.collections": None, "nemo.collections.asr": None}):
            with pytest.raises(RuntimeError, match="NeMo"):
                engine.load_model("parakeet-v3")

    def test_load_model_sets_model_size(self):
        engine = ParakeetEngine()
        with patch.dict("sys.modules", {"nemo": MagicMock(), "nemo.collections": MagicMock(), "nemo.collections.asr": MagicMock()}):
            engine.load_model("parakeet-v3", headless=True)

        assert engine._model_size == "parakeet-v3"
        assert engine.is_loaded()
