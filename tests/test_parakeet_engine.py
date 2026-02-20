"""Tests for ParakeetEngine (onnx-asr backend)."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from voxtype.stt.parakeet import (
    ParakeetEngine,
    _install_onnx_asr,
    _is_onnx_asr_installed,
    is_parakeet_model,
)

# ---------------------------------------------------------------------------
# is_parakeet_model
# ---------------------------------------------------------------------------

class TestIsParakeetModel:
    def test_parakeet_v3(self):
        assert is_parakeet_model("parakeet-v3") is True

    def test_parakeet_prefix(self):
        assert is_parakeet_model("parakeet-anything") is True

    def test_whisper_is_not_parakeet(self):
        assert is_parakeet_model("large-v3-turbo") is False

    def test_tiny_is_not_parakeet(self):
        assert is_parakeet_model("tiny") is False

# ---------------------------------------------------------------------------
# _is_onnx_asr_installed
# ---------------------------------------------------------------------------

class TestIsOnnxAsrInstalled:
    def test_returns_true_when_importable(self):
        with patch.dict("sys.modules", {"onnx_asr": MagicMock()}):
            assert _is_onnx_asr_installed() is True

    def test_returns_false_when_not_installed(self):
        with patch.dict("sys.modules", {"onnx_asr": None}):
            assert _is_onnx_asr_installed() is False

# ---------------------------------------------------------------------------
# _install_onnx_asr
# ---------------------------------------------------------------------------

class TestInstallOnnxAsr:
    def test_raises_when_user_declines_headless(self):
        """In headless mode (no console) we cannot prompt — but _install_onnx_asr
        is only called in interactive mode. Test that declining raises."""
        with patch("builtins.input", return_value="n"):
            with pytest.raises(RuntimeError, match="onnx-asr"):
                _install_onnx_asr(console=None)

    def test_runs_pip_when_confirmed(self):
        with patch("builtins.input", return_value="y"), \
             patch("subprocess.run") as mock_run, \
             patch("importlib.invalidate_caches"):
            mock_run.return_value = MagicMock(returncode=0)
            _install_onnx_asr(console=None)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "pip" in args
            assert "install" in args
            assert "onnx-asr" in args

    def test_raises_when_pip_fails(self):
        with patch("builtins.input", return_value="y"), \
             patch("subprocess.run") as mock_run, \
             patch("importlib.invalidate_caches"):
            mock_run.return_value = MagicMock(returncode=1)
            with pytest.raises(RuntimeError, match="Install failed"):
                _install_onnx_asr(console=None)

    def test_empty_input_means_yes(self):
        """Pressing Enter (default Y) should proceed with install."""
        with patch("builtins.input", return_value=""), \
             patch("subprocess.run") as mock_run, \
             patch("importlib.invalidate_caches"):
            mock_run.return_value = MagicMock(returncode=0)
            _install_onnx_asr(console=None)
            mock_run.assert_called_once()

# ---------------------------------------------------------------------------
# ParakeetEngine
# ---------------------------------------------------------------------------

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

    # --- load_model: headless mode ---

    def test_load_model_raises_in_headless_if_not_installed(self):
        engine = ParakeetEngine()
        with patch("voxtype.stt.parakeet._is_onnx_asr_installed", return_value=False):
            with pytest.raises(RuntimeError, match="voxtype stt install"):
                engine.load_model("parakeet-v3", headless=True)

    def test_load_model_calls_load_model_with_correct_name(self):
        mock_load = MagicMock(return_value=MagicMock())
        engine = ParakeetEngine()

        with patch("voxtype.stt.parakeet._is_onnx_asr_installed", return_value=True), \
             patch.dict("sys.modules", {"onnx_asr": MagicMock(load_model=mock_load)}):
            engine.load_model("parakeet-v3", headless=True)

        assert engine._model_size == "parakeet-v3"
        assert engine.is_loaded()
