"""Audio management for voxtype."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

from voxtype.audio.capture import AudioCapture

if TYPE_CHECKING:
    from voxtype.audio.vad import SileroVAD, StreamingVAD
    from voxtype.config import AudioConfig

class AudioManager:
    """Manages audio capture, VAD, and device reconnection.

    Encapsulates:
    - AudioCapture for microphone input
    - SileroVAD and StreamingVAD for voice activity detection
    - Audio device reconnection logic
    - Audio queue for buffered speech during transcription

    This class is UI-agnostic. Use event callbacks to receive notifications
    about loading progress, reconnection attempts, etc.
    """

    def __init__(
        self,
        config: AudioConfig,
        verbose: bool = False,
    ) -> None:
        """Initialize audio manager.

        Args:
            config: Audio configuration (sample_rate, channels, device, silence_ms, etc.)
            verbose: Enable verbose logging
        """
        self._config = config
        self._verbose = verbose

        # Audio components
        self._audio: AudioCapture | None = None
        self._vad: SileroVAD | None = None
        self._streaming_vad: StreamingVAD | None = None

        # Lock to synchronize VAD access during shutdown
        # Prevents race condition where callback uses VAD while close() deletes it
        self._vad_lock = threading.Lock()

        # Audio queue for buffered speech during transcription (thread-safe)
        self._audio_queue: Queue = Queue()

        # VAD callbacks
        self._on_speech_start: Callable[[], None] | None = None
        self._on_speech_end: Callable[[object], None] | None = None
        self._on_max_speech: Callable[[], None] | None = None
        self._on_partial_audio: Callable[[object], None] | None = None

        # Status callbacks (for UI notifications)
        self._on_vad_loading: Callable[[], None] | None = None
        self._on_reconnect_attempt: Callable[[int], None] | None = None
        self._on_reconnect_success: Callable[[str | None], None] | None = None

        # Listening state getter (set by start_streaming)
        self._is_listening: Callable[[], bool] | None = None
        self._is_running: Callable[[], bool] | None = None

    def initialize(
        self,
        on_speech_start: Callable[[], None],
        on_speech_end: Callable[[object], None],
        on_max_speech: Callable[[], None],
        on_partial_audio: Callable[[object], None] | None = None,
        on_vad_loading: Callable[[], None] | None = None,
    ) -> None:
        """Initialize audio capture and VAD components.

        Args:
            on_speech_start: Callback when VAD detects speech start
            on_speech_end: Callback when VAD detects speech end (with audio data)
            on_max_speech: Callback when max speech duration reached
            on_partial_audio: Callback for partial audio during speech (realtime feedback)
            on_vad_loading: Callback when VAD model starts loading
        """
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._on_max_speech = on_max_speech
        self._on_partial_audio = on_partial_audio
        self._on_vad_loading = on_vad_loading

        # Create audio capture
        self._audio = AudioCapture(
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
            device=self._config.device,
        )

        # Notify VAD loading start
        if self._on_vad_loading:
            self._on_vad_loading()

        # Create VAD components
        from voxtype.audio.vad import SileroVAD, StreamingVAD

        self._vad = SileroVAD(
            threshold=0.5,
            min_silence_ms=self._config.silence_ms,
            min_speech_ms=250,
        )
        # Pre-load the model now, not on first speech
        self._vad._load_model()

        # Create streaming VAD processor
        self._streaming_vad = StreamingVAD(
            vad=self._vad,
            on_speech_start=on_speech_start,
            on_speech_end=on_speech_end,
            max_speech_seconds=self._config.max_duration,
            on_max_speech=on_max_speech,
            on_partial_audio=on_partial_audio,
        )

    def set_reconnect_callbacks(
        self,
        on_attempt: Callable[[int], None] | None = None,
        on_success: Callable[[str | None], None] | None = None,
    ) -> None:
        """Set callbacks for device reconnection events.

        Args:
            on_attempt: Callback when reconnection attempt starts (receives attempt number 1-5)
            on_success: Callback when reconnection succeeds (receives device name or None)
        """
        self._on_reconnect_attempt = on_attempt
        self._on_reconnect_success = on_success

    def start_streaming(
        self,
        is_listening: Callable[[], bool],
        is_running: Callable[[], bool],
    ) -> None:
        """Start audio streaming.

        Args:
            is_listening: Callable that returns current listening state
            is_running: Callable that returns current running state
        """
        self._is_listening = is_listening
        self._is_running = is_running
        if self._audio:
            self._audio.start_streaming(self._on_audio_chunk)

    def stop_streaming(self) -> None:
        """Stop audio streaming."""
        if self._audio:
            if self._audio.is_recording():
                self._audio.stop_recording()
            self._audio.stop_streaming()

    def close(self) -> None:
        """Clean up all resources.

        Call this on shutdown to release ONNX session resources
        and avoid semaphore leak warnings.
        """
        # Stop the audio stream first to prevent new callbacks
        self.stop_streaming()

        # Acquire lock to ensure no callback is currently using VAD
        # This synchronizes with _on_audio_chunk() which also holds this lock
        with self._vad_lock:
            self._streaming_vad = None

        # Now close the VAD (safe because callbacks can't use it anymore)
        if self._vad:
            self._vad.close()
            self._vad = None

    def _on_audio_chunk(self, chunk: Any) -> None:
        """Process audio chunk through VAD."""
        # Only process if running AND listening
        is_running = self._is_running() if self._is_running else True
        is_listening = self._is_listening() if self._is_listening else False

        if not (is_running and is_listening):
            return

        # Use lock to prevent race condition with close()
        # This ensures VAD isn't deleted while we're using it
        with self._vad_lock:
            streaming_vad = self._streaming_vad
            if streaming_vad:
                streaming_vad.process_chunk(chunk)

    def needs_reconnect(self) -> bool:
        """Check if audio device needs reconnection."""
        return self._audio is not None and self._audio.needs_reconnect()

    def reconnect(self, on_chunk_callback: Callable[[Any], None]) -> bool:
        """Attempt to reconnect audio device.

        Args:
            on_chunk_callback: Callback for audio chunks after reconnection

        Returns:
            True if reconnection succeeded
        """
        import sounddevice as sd

        # Stop and destroy old audio capture
        if self._audio:
            try:
                self._audio.stop_streaming()
            except Exception:
                pass
            self._audio = None

        # Retry with fresh AudioCapture object using NEW default device
        for attempt in range(5):
            if self._on_reconnect_attempt:
                self._on_reconnect_attempt(attempt + 1)
            time.sleep(1.0)
            try:
                # Force PortAudio to refresh device list
                sd._terminate()
                sd._initialize()

                # Create new AudioCapture with default device (None)
                self._audio = AudioCapture(
                    sample_rate=self._config.sample_rate,
                    channels=self._config.channels,
                    device=None,  # Always use new default on reconnect
                )
                self._audio.start_streaming(on_chunk_callback)

                # Notify success with device name
                if self._on_reconnect_success:
                    device_info = AudioCapture.get_default_device()
                    device_name = device_info['name'] if device_info else None
                    self._on_reconnect_success(device_name)
                return True
            except Exception:
                self._audio = None
        return False

    def flush_vad(self) -> None:
        """Flush VAD state (discard current speech)."""
        if self._streaming_vad:
            self._streaming_vad.flush()

    def queue_audio(self, audio_data: object) -> None:
        """Add audio to queue for later processing.

        Args:
            audio_data: Audio data to queue
        """
        self._audio_queue.put(audio_data)

    def pop_queued_audio(self) -> Any | None:
        """Pop first audio from queue.

        Returns:
            Audio data or None if queue is empty
        """
        try:
            return self._audio_queue.get_nowait()
        except Empty:
            return None

    def clear_queue(self) -> None:
        """Clear audio queue."""
        while True:
            try:
                self._audio_queue.get_nowait()
            except Empty:
                break

    @property
    def has_queued_audio(self) -> bool:
        """Check if there's queued audio."""
        return not self._audio_queue.empty()

    @property
    def queued_count(self) -> int:
        """Get number of queued audio items."""
        return self._audio_queue.qsize()

    @property
    def sample_rate(self) -> int:
        """Get audio sample rate."""
        return self._config.sample_rate
