"""Voice Activity Detection using Silero VAD."""

from __future__ import annotations

import importlib.util
import logging
import os
import time as _time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from numpy.typing import NDArray


def _find_silero_model_path() -> str:
    """Locate silero_vad_v6.onnx from the faster-whisper package.

    Uses importlib to find the package path WITHOUT importing it,
    avoiding the 20+ second ctranslate2 import on first run after install.
    """
    spec = importlib.util.find_spec("faster_whisper")
    if spec is None or spec.submodule_search_locations is None:
        raise RuntimeError(
            "faster-whisper package not installed — cannot find silero VAD model"
        )
    path = os.path.join(spec.submodule_search_locations[0], "assets", "silero_vad_v6.onnx")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Silero VAD model not found: {path}")
    return path


def _create_vad_session() -> Any:
    """Create an ONNX InferenceSession for silero VAD.

    Loads onnxruntime directly instead of going through faster_whisper,
    which would trigger a slow ctranslate2 import.
    """
    import onnxruntime

    model_path = _find_silero_model_path()
    opts = onnxruntime.SessionOptions()
    opts.inter_op_num_threads = 1
    opts.intra_op_num_threads = 1
    opts.enable_cpu_mem_arena = False
    opts.log_severity_level = 4

    return onnxruntime.InferenceSession(
        model_path,
        providers=["CPUExecutionProvider"],
        sess_options=opts,
    )


class _DirectVADModel:
    """Minimal wrapper matching faster_whisper.vad.SileroVADModel interface.

    Only exposes `.session` — the single attribute used by SileroVAD.is_speech().
    """

    __slots__ = ("session",)

    def __init__(self, session: Any) -> None:
        self.session = session


class VADEngine(ABC):
    """Abstract Voice Activity Detection interface."""

    @abstractmethod
    def is_speech(self, audio_chunk: NDArray[np.float32]) -> float:
        """Check if audio chunk contains speech.

        Args:
            audio_chunk: Audio samples (float32, mono, 16kHz).

        Returns:
            Speech probability (0.0 to 1.0).
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset VAD state."""
        pass


class SileroVAD(VADEngine):
    """Silero VAD implementation using the bundled ONNX model."""

    # Silero VAD processes 512 samples at a time (32ms at 16kHz)
    CHUNK_SIZE = 512

    def __init__(
        self,
        threshold: float = 0.5,
        neg_threshold: float = 0.35,
        min_silence_ms: int = 700,
        min_speech_ms: int = 250,
        sample_rate: int = 16000,
    ) -> None:
        """Initialize Silero VAD.

        Args:
            threshold: Speech probability threshold (0.0-1.0).
            neg_threshold: Threshold below which is definitely silence.
            min_silence_ms: Minimum silence duration to end speech segment.
            min_speech_ms: Minimum speech duration to be valid.
            sample_rate: Audio sample rate (must be 16000).
        """
        self.threshold = threshold
        self.neg_threshold = neg_threshold
        self.min_silence_ms = min_silence_ms
        self.min_speech_ms = min_speech_ms
        self.sample_rate = sample_rate

        # Model will be loaded lazily
        self._model: Any = None

        # State for streaming VAD
        self._h: Any = None
        self._c: Any = None
        self._context: Any = None

    def _load_model(self, with_indicator: bool = False, *, headless: bool = False) -> None:
        """Load the Silero VAD model.

        Loads the ONNX model directly via onnxruntime, bypassing the
        faster_whisper import chain (which pulls in ctranslate2 and takes
        20+ seconds on first run after install).

        Args:
            with_indicator: If True, show loading progress indicator (ignored if headless).
            headless: If True, skip all console output (for Engine/daemon mode).
        """
        if self._model is not None:
            return

        def load_vad_fn():
            _t = _time.monotonic()
            session = _create_vad_session()
            elapsed = _time.monotonic() - _t
            logger.info("VAD: ONNX session created in %.2fs", elapsed)
            return _DirectVADModel(session)

        if with_indicator or headless:
            # Use load_with_indicator for stats tracking, but headless mode suppresses UI
            from dictare.utils.loading import load_with_indicator

            self._model = load_with_indicator(
                "silero-vad",
                "VAD model",
                load_vad_fn,
                headless=headless,
            )
        else:
            self._model = load_vad_fn()

        self.reset()

    def close(self) -> None:
        """Release ONNX session resources.

        Sets self._model = None atomically.  Any in-flight callback that
        already captured a local reference will finish safely; the ONNX
        session is freed by gc once all references are dropped.

        Previous code did ``del self._model.session`` before setting
        ``self._model = None``, creating a window where another thread
        could see a model object without a session → AttributeError.
        """
        import gc

        self._model = None
        gc.collect()

    def reset(self) -> None:
        """Reset VAD hidden state."""
        self._h = np.zeros((1, 1, 128), dtype="float32")
        self._c = np.zeros((1, 1, 128), dtype="float32")
        self._context = np.zeros((1, 64), dtype="float32")

    def is_speech(self, audio_chunk: NDArray[np.float32]) -> float:
        """Process a single 512-sample chunk and return speech probability.

        Args:
            audio_chunk: Exactly 512 float32 samples.

        Returns:
            Speech probability (0.0 to 1.0).
        """
        self._load_model()

        if len(audio_chunk) != self.CHUNK_SIZE:
            raise ValueError(f"Chunk must be {self.CHUNK_SIZE} samples, got {len(audio_chunk)}")

        # Prepare input with context
        x = np.concatenate([self._context[0], audio_chunk])[np.newaxis, :]

        # Run inference
        out, self._h, self._c = self._model.session.run(
            None,
            {
                "input": x.astype(np.float32),
                "h": self._h,
                "c": self._c,
            },
        )

        # Update context for next chunk
        self._context = x[:, -64:]

        # Handle different output shapes
        if out.ndim == 2:
            return float(out[0, 0])
        elif out.ndim == 1:
            return float(out[0])
        else:
            return float(out.flat[0])


class StreamingVAD:
    """Streaming VAD processor that detects speech segments."""

    def __init__(
        self,
        vad: SileroVAD,
        on_speech_start: Callable[[], None],
        on_speech_end: Callable[[NDArray[np.float32]], None],
        max_speech_seconds: int = 60,
        on_max_speech: Callable[[], None] | None = None,
        on_partial_audio: Callable[[NDArray[np.float32]], None] | None = None,
        partial_interval_ms: int = 1000,
        pre_buffer_ms: int = 640,
    ) -> None:
        """Initialize streaming VAD.

        Args:
            vad: SileroVAD instance.
            on_speech_start: Called when speech starts.
            on_speech_end: Called when speech ends, with accumulated audio.
            max_speech_seconds: Max duration before forced send (default 60s).
            on_max_speech: Called when max speech duration reached (for beep).
            on_partial_audio: Called periodically with accumulated audio (for realtime feedback).
            partial_interval_ms: Interval between partial audio callbacks (default 1000ms).
            pre_buffer_ms: Pre-buffer duration in ms to capture audio before speech (default 640ms).
        """
        self.vad = vad
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end
        self.max_speech_samples = max_speech_seconds * vad.sample_rate
        self.on_max_speech = on_max_speech
        self.on_partial_audio = on_partial_audio
        self._partial_interval_samples = partial_interval_ms * vad.sample_rate // 1000

        # State
        self._is_speaking = False
        self._audio_buffer: list[NDArray[np.float32]] = []
        self._silence_samples = 0
        self._speech_samples = 0
        self._total_speech_samples = 0  # Track total for max duration
        self._samples_since_partial = 0  # Track samples since last partial callback

        # Periodic VAD reset: after prolonged silence, reset LSTM hidden state
        # to prevent numerical drift. 5 minutes of silence = 5*60*16000 samples.
        self._silence_total_samples = 0
        self._silence_reset_threshold = 5 * 60 * vad.sample_rate  # 5 minutes

        # Pre-buffer for capturing audio just before speech starts
        self._pre_buffer: list[NDArray[np.float32]] = []
        chunk_ms = SileroVAD.CHUNK_SIZE * 1000 // vad.sample_rate  # ~32ms
        self._pre_buffer_chunks = max(1, pre_buffer_ms // chunk_ms)

    def process_chunk(self, chunk: NDArray[np.float32]) -> None:
        """Process an audio chunk (512 samples).

        Args:
            chunk: Audio samples (512 float32 samples).
        """
        prob = self.vad.is_speech(chunk)

        # Track prolonged silence and periodically reset LSTM state
        if not self._is_speaking:
            if prob < self.vad.threshold:
                self._silence_total_samples += len(chunk)
                if self._silence_total_samples >= self._silence_reset_threshold:
                    self.vad.reset()
                    self._silence_total_samples = 0
            else:
                self._silence_total_samples = 0

        if not self._is_speaking:
            # Not currently speaking - look for speech start
            self._pre_buffer.append(chunk.copy())
            if len(self._pre_buffer) > self._pre_buffer_chunks:
                self._pre_buffer.pop(0)

            if prob >= self.vad.threshold:
                self._speech_samples += len(chunk)

                # Check if we have enough speech to trigger
                min_samples = self.vad.sample_rate * self.vad.min_speech_ms // 1000
                if self._speech_samples >= min_samples:
                    self._is_speaking = True
                    self._speech_samples = 0
                    self._silence_samples = 0

                    # Include pre-buffer
                    self._audio_buffer = list(self._pre_buffer)
                    self._pre_buffer = []

                    self.on_speech_start()
            else:
                self._speech_samples = 0
        else:
            # Currently speaking - accumulate audio
            self._audio_buffer.append(chunk.copy())
            self._total_speech_samples += len(chunk)
            self._samples_since_partial += len(chunk)

            # Call partial audio callback periodically for realtime feedback
            if self.on_partial_audio and self._samples_since_partial >= self._partial_interval_samples:
                self._samples_since_partial = 0
                if self._audio_buffer:
                    audio = np.concatenate(self._audio_buffer)
                    self.on_partial_audio(audio)

            # Check max speech duration (send partial, continue listening)
            if self._total_speech_samples >= self.max_speech_samples:
                if self._audio_buffer:
                    audio = np.concatenate(self._audio_buffer)
                    self._audio_buffer = []
                    self._total_speech_samples = 0
                    # Don't reset VAD state - we're still speaking
                    # Notify for beep, then send audio
                    if self.on_max_speech:
                        self.on_max_speech()
                    self.on_speech_end(audio)
                return

            if prob < self.vad.neg_threshold:
                self._silence_samples += len(chunk)

                # Check if silence is long enough to end speech
                min_silence = self.vad.sample_rate * self.vad.min_silence_ms // 1000
                if self._silence_samples >= min_silence:
                    self._is_speaking = False
                    self._silence_samples = 0
                    self._total_speech_samples = 0

                    # Combine audio and call callback
                    if self._audio_buffer:
                        audio = np.concatenate(self._audio_buffer)
                        self._audio_buffer = []
                        self.vad.reset()
                        self.on_speech_end(audio)
            else:
                self._silence_samples = 0

    def process_audio(self, audio: NDArray[np.float32]) -> None:
        """Process arbitrary-length audio by splitting into chunks.

        Args:
            audio: Audio samples (float32).
        """
        chunk_size = SileroVAD.CHUNK_SIZE
        for i in range(0, len(audio) - chunk_size + 1, chunk_size):
            self.process_chunk(audio[i:i + chunk_size])

    def flush(self) -> None:
        """Flush any remaining audio if currently speaking."""
        if self._is_speaking and self._audio_buffer:
            audio = np.concatenate(self._audio_buffer)
            self._audio_buffer = []
            self._is_speaking = False
            self.vad.reset()
            self.on_speech_end(audio)

    def reset(self) -> None:
        """Reset streaming state (discard accumulated audio)."""
        self._is_speaking = False
        self._audio_buffer = []
        self._silence_samples = 0
        self._speech_samples = 0
        self._total_speech_samples = 0
        self._samples_since_partial = 0
        self._silence_total_samples = 0
        self._pre_buffer = []
        self.vad.reset()
