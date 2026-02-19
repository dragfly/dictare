"""Audio management for voxtype."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from queue import Empty, Full, Queue
from typing import TYPE_CHECKING, Any

from voxtype.audio.capture import AudioCapture

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from voxtype.audio.device_monitor import DeviceMonitor
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
        # Bounded to prevent memory exhaustion if events come faster than processing
        self._audio_queue: Queue = Queue(maxsize=10)

        # VAD callbacks
        self._on_speech_start: Callable[[], None] | None = None
        self._on_speech_end: Callable[[object], None] | None = None
        self._on_max_speech: Callable[[], None] | None = None
        self._on_partial_audio: Callable[[object], None] | None = None

        # Status callbacks (for UI notifications)
        self._on_vad_loading: Callable[[], None] | None = None
        self._on_reconnect_attempt: Callable[[int], None] | None = None
        self._on_reconnect_success: Callable[[str | None], None] | None = None

        # Device monitor (detects device changes at OS level)
        self._device_monitor: DeviceMonitor | None = None

        # State check callbacks (set by start_streaming)
        # These are internal - use the properties should_process_audio / is_engine_running
        self._should_process_check: Callable[[], bool] | None = None
        self._is_running_check: Callable[[], bool] | None = None

    @property
    def should_process_audio(self) -> bool:
        """Check if audio should be processed (engine is listening)."""
        if self._should_process_check is None:
            return False
        return self._should_process_check()

    @property
    def is_engine_running(self) -> bool:
        """Check if engine is running."""
        if self._is_running_check is None:
            return True  # Default to running if not set
        return self._is_running_check()

    def initialize(
        self,
        on_speech_start: Callable[[], None],
        on_speech_end: Callable[[object], None],
        on_max_speech: Callable[[], None],
        on_partial_audio: Callable[[object], None] | None = None,
        on_vad_loading: Callable[[], None] | None = None,
        *,
        headless: bool = False,
    ) -> None:
        """Initialize audio capture and VAD components.

        Args:
            on_speech_start: Callback when VAD detects speech start
            on_speech_end: Callback when VAD detects speech end (with audio data)
            on_max_speech: Callback when max speech duration reached
            on_partial_audio: Callback for partial audio during speech (realtime feedback)
            on_vad_loading: Callback when VAD model starts loading
            headless: If True, skip all console output (for Engine/daemon mode)
        """
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._on_max_speech = on_max_speech
        self._on_partial_audio = on_partial_audio
        self._on_vad_loading = on_vad_loading

        # Create audio capture
        self._audio = AudioCapture(
            sample_rate=self._config.advanced.sample_rate,
            channels=self._config.advanced.channels,
            device=self._config.advanced.device,
        )

        # Create device monitor (detects OS-level device changes before PortAudio crashes)
        from voxtype.audio.device_monitor import create_device_monitor

        self._device_monitor = create_device_monitor(
            on_device_change=self._on_device_change,
        )

        # Notify VAD loading start
        if self._on_vad_loading:
            self._on_vad_loading()

        # Create VAD components
        from voxtype.audio.vad import SileroVAD, StreamingVAD

        self._vad = SileroVAD(
            threshold=0.5,
            min_silence_ms=self._config.silence_ms,
            min_speech_ms=self._config.advanced.min_speech_ms,
        )
        # Pre-load the model now (headless mode skips progress indicator)
        self._vad._load_model(with_indicator=not headless, headless=headless)

        # Create streaming VAD processor
        self._streaming_vad = StreamingVAD(
            vad=self._vad,
            on_speech_start=on_speech_start,
            on_speech_end=on_speech_end,
            max_speech_seconds=self._config.max_duration,
            on_max_speech=on_max_speech,
            on_partial_audio=on_partial_audio,
            pre_buffer_ms=self._config.advanced.pre_buffer_ms,
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
        should_process: Callable[[], bool],
        is_running: Callable[[], bool],
    ) -> None:
        """Start audio streaming.

        Args:
            should_process: Callable that returns True if audio should be processed
            is_running: Callable that returns True if engine is running
        """
        self._should_process_check = should_process
        self._is_running_check = is_running
        if self._audio:
            self._audio.start_streaming(self._on_audio_chunk)
        if self._device_monitor:
            self._device_monitor.start()

    def stop_streaming(self) -> None:
        """Stop audio streaming."""
        if self._audio:
            if self._audio.is_recording():
                self._audio.stop_recording()
            self._audio.stop_streaming()

    def _on_device_change(self) -> None:
        """Handle OS-level device change notification.

        Called from CoreAudio thread (macOS) or polling thread (Linux).
        Must be fast and safe for any thread.
        """
        logger.info("Audio device change detected, aborting stream")
        if self._audio:
            self._audio.emergency_abort()

    def close(self) -> None:
        """Clean up all resources.

        Call this on shutdown to release ONNX session resources
        and avoid semaphore leak warnings.
        """
        # Stop device monitor first
        if self._device_monitor:
            self._device_monitor.stop()
            self._device_monitor = None

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
        # Only process if engine is running AND should process audio
        if not (self.is_engine_running and self.should_process_audio):
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

        # Stop device monitor during reconnection
        if self._device_monitor:
            self._device_monitor.stop()

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
                    sample_rate=self._config.advanced.sample_rate,
                    channels=self._config.advanced.channels,
                    device=None,  # Always use new default on reconnect
                )
                self._audio.start_streaming(on_chunk_callback)

                # Reset VAD state for new device (LSTM hidden state from old
                # device's noise floor can prevent speech detection)
                self.reset_vad()

                # Restart device monitor for the new stream
                if self._device_monitor:
                    self._device_monitor.start()

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
        """Flush VAD state (send buffered audio as speech_end)."""
        with self._vad_lock:
            if self._streaming_vad:
                self._streaming_vad.flush()

    def reset_vad(self) -> None:
        """Reset VAD state (discard buffered audio without processing)."""
        with self._vad_lock:
            if self._streaming_vad:
                self._streaming_vad.reset()

    def queue_audio(self, audio_data: object) -> None:
        """Add audio to queue for later processing.

        Args:
            audio_data: Audio data to queue

        Note:
            If queue is full (>10 items), oldest audio is discarded.
            This prevents memory exhaustion under heavy load.
        """
        try:
            self._audio_queue.put_nowait(audio_data)
        except Full:
            # Queue full - discard oldest and add new
            try:
                self._audio_queue.get_nowait()
            except Empty:
                pass
            try:
                self._audio_queue.put_nowait(audio_data)
            except Full:
                pass  # Still full, drop this audio

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
        return self._config.advanced.sample_rate
