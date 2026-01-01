"""Voice Activity Detection using Silero VAD."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


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
    """Silero VAD implementation using faster-whisper's bundled model."""

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
        self._model = None

        # State for streaming VAD
        self._h = None
        self._c = None
        self._context = None

    def _load_model(self) -> None:
        """Load the Silero VAD model."""
        if self._model is not None:
            return

        from faster_whisper.vad import get_vad_model
        self._model = get_vad_model()
        self.reset()

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
    ) -> None:
        """Initialize streaming VAD.

        Args:
            vad: SileroVAD instance.
            on_speech_start: Called when speech starts.
            on_speech_end: Called when speech ends, with accumulated audio.
        """
        self.vad = vad
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end

        # State
        self._is_speaking = False
        self._audio_buffer: list[NDArray[np.float32]] = []
        self._silence_samples = 0
        self._speech_samples = 0

        # Pre-buffer for capturing audio just before speech starts
        self._pre_buffer: list[NDArray[np.float32]] = []
        self._pre_buffer_chunks = 10  # ~320ms at 512 samples/chunk

    def process_chunk(self, chunk: NDArray[np.float32]) -> None:
        """Process an audio chunk (512 samples).

        Args:
            chunk: Audio samples (512 float32 samples).
        """
        prob = self.vad.is_speech(chunk)

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

            if prob < self.vad.neg_threshold:
                self._silence_samples += len(chunk)

                # Check if silence is long enough to end speech
                min_silence = self.vad.sample_rate * self.vad.min_silence_ms // 1000
                if self._silence_samples >= min_silence:
                    self._is_speaking = False
                    self._silence_samples = 0

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
        self._pre_buffer = []
        self.vad.reset()
