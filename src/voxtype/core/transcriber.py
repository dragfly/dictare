"""One-shot audio transcription for pipe/scripting use."""

from __future__ import annotations

import signal
import sys
import threading
import time
from typing import TYPE_CHECKING

import numpy as np

from voxtype.audio.capture import AudioCapture
from voxtype.audio.vad import SileroVAD, StreamingVAD
from voxtype.stt.base import STTEngine

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from voxtype.config import Config


class OneShotTranscriber:
    """Records audio until speech ends, then transcribes.

    Designed for one-shot use in scripts and pipes:
        voxtype transcribe | llm "respond to this"
    """

    def __init__(
        self,
        config: Config,
        stt_engine: STTEngine,
        silence_ms: int = 1200,
        max_duration: int = 60,
        quiet: bool = False,
    ) -> None:
        """Initialize transcriber.

        Args:
            config: Voxtype configuration.
            stt_engine: Loaded STT engine.
            silence_ms: Silence duration to end recording (ms).
            max_duration: Maximum recording duration (seconds).
            quiet: Suppress status messages.
        """
        self.config = config
        self.stt_engine = stt_engine
        self.silence_ms = silence_ms
        self.max_duration = max_duration
        self.quiet = quiet

        # State
        self._audio_data: NDArray[np.float32] | None = None
        self._speech_started = False
        self._done = threading.Event()
        self._cancelled = threading.Event()
        self._start_time: float = 0
        self._audio_capture: AudioCapture | None = None

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle SIGINT to cleanly stop recording."""
        self._cancelled.set()
        self._done.set()
        if self._audio_capture:
            self._audio_capture.stop_streaming()

    def record_and_transcribe(self) -> str:
        """Record audio with VAD and transcribe.

        Blocks until speech is detected and ends, or max duration reached.

        Returns:
            Transcribed text.
        """
        # Set up signal handler for clean Ctrl+C
        old_handler = signal.signal(signal.SIGINT, self._signal_handler)

        try:
            # Create components
            self._audio_capture = AudioCapture(
                sample_rate=self.config.audio.sample_rate,
                channels=self.config.audio.channels,
                device=self.config.audio.device,
            )

            vad = SileroVAD(
                threshold=0.5,
                neg_threshold=0.35,
                min_silence_ms=self.silence_ms,
                min_speech_ms=250,
                sample_rate=self.config.audio.sample_rate,
            )

            streaming_vad = StreamingVAD(
                vad=vad,
                on_speech_start=self._on_speech_start,
                on_speech_end=self._on_speech_end,
            )

            # Start streaming audio through VAD
            if not self.quiet:
                print("[Waiting for speech...]", file=sys.stderr)
            self._start_time = time.time()

            self._audio_capture.start_streaming(streaming_vad.process_chunk)

            # Wait for speech to end or timeout
            while not self._done.is_set() and not self._cancelled.is_set():
                elapsed = time.time() - self._start_time
                if elapsed > self.max_duration:
                    if not self.quiet:
                        print(f"\n[Max duration {self.max_duration}s reached]", file=sys.stderr)
                    streaming_vad.flush()
                    break
                # Use wait with timeout instead of sleep for faster interrupt response
                self._done.wait(timeout=0.1)

            self._audio_capture.stop_streaming()

            # Check if cancelled
            if self._cancelled.is_set():
                if not self.quiet:
                    print("\n[Cancelled]", file=sys.stderr)
                return ""

            # Transcribe
            if self._audio_data is None or len(self._audio_data) == 0:
                return ""

            if not self.quiet:
                print("[Transcribing...]", file=sys.stderr)
            result = self.stt_engine.transcribe(
                self._audio_data,
                language=self.config.stt.language,
                beam_size=self.config.stt.beam_size,
                max_repetitions=self.config.stt.max_repetitions,
            )

            return result.text.strip()

        finally:
            # Restore original signal handler
            signal.signal(signal.SIGINT, old_handler)
            if self._audio_capture:
                self._audio_capture.stop_streaming()

    def _on_speech_start(self) -> None:
        """Called when VAD detects speech start."""
        self._speech_started = True
        if not self.quiet:
            print("[Listening...]", file=sys.stderr)

    def _on_speech_end(self, audio: NDArray[np.float32]) -> None:
        """Called when VAD detects speech end."""
        self._audio_data = audio
        self._done.set()
