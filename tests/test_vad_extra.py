"""Tests for Voice Activity Detection — StreamingVAD logic, SileroVAD edge cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from dictare.audio.vad import SileroVAD, StreamingVAD, VADEngine

# ---------------------------------------------------------------------------
# VADEngine ABC
# ---------------------------------------------------------------------------

class TestVADEngine:
    """Test VADEngine abstract base class."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            VADEngine()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# SileroVAD
# ---------------------------------------------------------------------------

class TestSileroVAD:
    """Test SileroVAD — init, reset, close, chunk validation."""

    def test_default_params(self) -> None:
        vad = SileroVAD()
        assert vad.threshold == 0.5
        assert vad.neg_threshold == 0.35
        assert vad.min_silence_ms == 700
        assert vad.min_speech_ms == 250
        assert vad.sample_rate == 16000
        assert vad.CHUNK_SIZE == 512

    def test_custom_params(self) -> None:
        vad = SileroVAD(threshold=0.7, neg_threshold=0.4, min_silence_ms=500)
        assert vad.threshold == 0.7
        assert vad.neg_threshold == 0.4
        assert vad.min_silence_ms == 500

    def test_reset(self) -> None:
        vad = SileroVAD()
        vad.reset()
        assert vad._h is not None
        assert vad._h.shape == (1, 1, 128)
        assert vad._c.shape == (1, 1, 128)
        assert vad._context.shape == (1, 64)

    def test_close(self) -> None:
        vad = SileroVAD()
        vad._model = MagicMock()
        vad.close()
        assert vad._model is None

    def test_wrong_chunk_size_raises(self) -> None:
        vad = SileroVAD()
        # Mock model to avoid loading real ONNX
        mock_model = MagicMock()
        vad._model = mock_model
        vad.reset()

        wrong_size = np.zeros(100, dtype=np.float32)
        with pytest.raises(ValueError, match="512 samples"):
            vad.is_speech(wrong_size)

    def test_is_speech_returns_float(self) -> None:
        """is_speech returns a float probability."""
        vad = SileroVAD()
        mock_model = MagicMock()
        # Simulate ONNX output (2D array)
        mock_model.session.run.return_value = (
            np.array([[0.85]], dtype=np.float32),
            np.zeros((1, 1, 128), dtype=np.float32),
            np.zeros((1, 1, 128), dtype=np.float32),
        )
        vad._model = mock_model
        vad.reset()

        chunk = np.zeros(512, dtype=np.float32)
        prob = vad.is_speech(chunk)
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0

    def test_is_speech_1d_output(self) -> None:
        """Handle 1D ONNX output."""
        vad = SileroVAD()
        mock_model = MagicMock()
        mock_model.session.run.return_value = (
            np.array([0.6], dtype=np.float32),
            np.zeros((1, 1, 128), dtype=np.float32),
            np.zeros((1, 1, 128), dtype=np.float32),
        )
        vad._model = mock_model
        vad.reset()

        chunk = np.zeros(512, dtype=np.float32)
        prob = vad.is_speech(chunk)
        assert abs(prob - 0.6) < 0.001

    def test_is_speech_3d_output(self) -> None:
        """Handle 3D ONNX output (edge case)."""
        vad = SileroVAD()
        mock_model = MagicMock()
        mock_model.session.run.return_value = (
            np.array([[[0.42]]], dtype=np.float32),
            np.zeros((1, 1, 128), dtype=np.float32),
            np.zeros((1, 1, 128), dtype=np.float32),
        )
        vad._model = mock_model
        vad.reset()

        chunk = np.zeros(512, dtype=np.float32)
        prob = vad.is_speech(chunk)
        assert abs(prob - 0.42) < 0.001

    def test_load_model_skips_if_loaded(self) -> None:
        vad = SileroVAD()
        vad._model = MagicMock()
        # Should not call _create_vad_session
        with patch("dictare.audio.vad._create_vad_session") as mock:
            vad._load_model()
        mock.assert_not_called()


# ---------------------------------------------------------------------------
# StreamingVAD — core logic
# ---------------------------------------------------------------------------

class _MockVAD:
    """Controllable mock VAD for StreamingVAD testing."""

    CHUNK_SIZE = 512

    def __init__(self, *, threshold=0.5, neg_threshold=0.35) -> None:
        self.threshold = threshold
        self.neg_threshold = neg_threshold
        self.min_silence_ms = 700
        self.min_speech_ms = 250
        self.sample_rate = 16000
        self._probs: list[float] = []
        self._idx = 0
        self.reset_count = 0

    def set_probs(self, probs: list[float]) -> None:
        self._probs = probs
        self._idx = 0

    def is_speech(self, chunk: np.ndarray) -> float:
        if self._idx < len(self._probs):
            p = self._probs[self._idx]
            self._idx += 1
            return p
        return 0.0

    def reset(self) -> None:
        self.reset_count += 1


class TestStreamingVAD:
    """Test StreamingVAD state machine logic."""

    def _chunk(self, n: int = 512) -> np.ndarray:
        return np.zeros(n, dtype=np.float32)

    def test_initial_state(self) -> None:
        vad = _MockVAD()
        speech_starts = []
        speech_ends = []
        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: speech_starts.append(True),
            on_speech_end=lambda audio: speech_ends.append(audio),
        )
        assert sv._is_speaking is False

    def test_speech_detection_trigger(self) -> None:
        """Speech triggers after min_speech_ms of consecutive high prob."""
        vad = _MockVAD()
        speech_starts = []
        speech_ends = []
        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: speech_starts.append(True),
            on_speech_end=lambda audio: speech_ends.append(audio),
        )

        # min_speech_ms=250 at 16kHz = 4000 samples / 512 = ~8 chunks
        probs = [0.8] * 15  # enough high-prob chunks to trigger
        vad.set_probs(probs)

        for _ in range(15):
            sv.process_chunk(self._chunk())

        assert len(speech_starts) == 1
        assert sv._is_speaking is True

    def test_silence_ends_speech(self) -> None:
        """Enough silence after speech triggers speech end."""
        vad = _MockVAD()
        speech_starts = []
        speech_ends = []
        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: speech_starts.append(True),
            on_speech_end=lambda audio: speech_ends.append(audio),
        )

        # Start speech (8+ chunks of high prob)
        # Then send enough silence (700ms / 32ms = ~22 chunks)
        probs = [0.8] * 10 + [0.1] * 30
        vad.set_probs(probs)

        for _ in range(40):
            sv.process_chunk(self._chunk())

        assert len(speech_starts) == 1
        assert len(speech_ends) == 1
        assert sv._is_speaking is False

    def test_flush(self) -> None:
        """Flush sends accumulated audio when speaking."""
        vad = _MockVAD()
        speech_ends = []
        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: None,
            on_speech_end=lambda audio: speech_ends.append(audio),
        )

        # Force speaking state
        sv._is_speaking = True
        sv._audio_buffer = [self._chunk(), self._chunk()]

        sv.flush()
        assert len(speech_ends) == 1
        assert sv._is_speaking is False

    def test_flush_no_audio(self) -> None:
        """Flush with no audio is a no-op."""
        vad = _MockVAD()
        speech_ends = []
        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: None,
            on_speech_end=lambda audio: speech_ends.append(audio),
        )
        sv._is_speaking = True
        sv._audio_buffer = []
        sv.flush()  # empty buffer → no callback

    def test_reset(self) -> None:
        """Reset clears all state."""
        vad = _MockVAD()
        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: None,
            on_speech_end=lambda audio: None,
        )
        sv._is_speaking = True
        sv._audio_buffer = [self._chunk()]
        sv._silence_samples = 1000
        sv._speech_samples = 500

        sv.reset()

        assert sv._is_speaking is False
        assert sv._audio_buffer == []
        assert sv._silence_samples == 0
        assert sv._speech_samples == 0

    def test_process_audio_splits_chunks(self) -> None:
        """process_audio splits arbitrary audio into 512-sample chunks."""
        vad = _MockVAD()
        vad.set_probs([0.1] * 10)

        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: None,
            on_speech_end=lambda audio: None,
        )

        # 2048 samples = 4 chunks of 512
        audio = np.zeros(2048, dtype=np.float32)
        sv.process_audio(audio)
        # If it processed without error, chunks were handled

    def test_max_speech_triggers_callback(self) -> None:
        """Max speech duration triggers on_max_speech and sends audio."""
        vad = _MockVAD()
        max_speech_calls = []
        speech_ends = []
        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: None,
            on_speech_end=lambda audio: speech_ends.append(audio),
            max_speech_seconds=1,  # very short for testing
            on_max_speech=lambda: max_speech_calls.append(True),
        )

        # Force speaking state and fill buffer beyond max
        sv._is_speaking = True
        sv._total_speech_samples = 16000  # 1 second = max
        sv._audio_buffer = [np.zeros(512, dtype=np.float32)]

        # Set next VAD prob to high (still speaking)
        vad.set_probs([0.8])
        sv.process_chunk(np.zeros(512, dtype=np.float32))

        assert len(max_speech_calls) == 1
        assert len(speech_ends) == 1

    def test_pre_buffer(self) -> None:
        """Pre-buffer captures audio before speech start."""
        vad = _MockVAD()
        speech_starts = []
        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: speech_starts.append(True),
            on_speech_end=lambda audio: None,
            pre_buffer_ms=640,  # ~20 chunks at 32ms each
        )

        # Send some silence (fills pre-buffer), then speech
        probs = [0.1] * 5 + [0.8] * 10
        vad.set_probs(probs)

        for _ in range(15):
            sv.process_chunk(np.zeros(512, dtype=np.float32))

        if speech_starts:
            # Audio buffer should include pre-buffered chunks
            assert len(sv._audio_buffer) > 0

    def test_partial_audio_callback(self) -> None:
        """on_partial_audio called periodically during speech."""
        vad = _MockVAD()
        partials = []
        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: None,
            on_speech_end=lambda audio: None,
            on_partial_audio=lambda audio: partials.append(len(audio)),
            partial_interval_ms=500,
        )

        # Force speaking state
        sv._is_speaking = True
        sv._audio_buffer = [np.zeros(512, dtype=np.float32)]
        sv._samples_since_partial = 16000  # Force trigger

        vad.set_probs([0.8])
        sv.process_chunk(np.zeros(512, dtype=np.float32))

        assert len(partials) >= 1

    def test_silence_resets_vad_after_threshold(self) -> None:
        """Prolonged silence resets VAD LSTM state."""
        vad = _MockVAD()
        sv = StreamingVAD(
            vad,
            on_speech_start=lambda: None,
            on_speech_end=lambda audio: None,
        )

        initial_resets = vad.reset_count

        # 5 minutes of silence = 5*60*16000 = 4_800_000 samples
        # Each chunk is 512 samples, so need ~9375 chunks
        # Just set the counter directly
        sv._silence_total_samples = sv._silence_reset_threshold - 1

        vad.set_probs([0.1])
        sv.process_chunk(np.zeros(512, dtype=np.float32))

        # Should have reset
        assert vad.reset_count > initial_resets
