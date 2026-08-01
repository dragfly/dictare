"""Audio management for dictare."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from queue import Empty, Full, Queue
from typing import TYPE_CHECKING, Any

from dictare.audio.capture import AudioCapture, PortAudioCallTimeoutError, _run_with_timeout
from dictare.audio.supervisor import (
    AudioControl,
    AudioControlClosedError,
    AudioControlPoisonedError,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dictare.audio.device_monitor import DeviceMonitor
    from dictare.audio.vad import SileroVAD, StreamingVAD
    from dictare.config import AudioConfig

class AudioManager:
    """Manages audio capture, VAD, and device reconnection.

    Encapsulates:
    - AudioCapture for microphone input
    - SileroVAD and StreamingVAD for voice activity detection
    - Audio device reconnection logic with circuit breaker
    - Audio queue for buffered speech during transcription

    This class is UI-agnostic. Use event callbacks to receive notifications
    about loading progress, reconnection attempts, etc.
    """

    # Circuit breaker: stop reconnecting if too many attempts in a window
    _MAX_RECONNECTS = 5
    _RECONNECT_WINDOW_S = 60.0
    _RECONNECT_COOLDOWN_S = 3.0

    def __init__(
        self,
        config: AudioConfig,
        verbose: bool = False,
        on_poisoned: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize audio manager.

        Args:
            config: Audio configuration (sample_rate, channels, device, silence_ms, etc.)
            verbose: Enable verbose logging
        """
        self._config = config
        self._verbose = verbose
        self._control = AudioControl(on_poisoned=on_poisoned)
        self._device_change_lock = threading.Lock()
        self._device_change_reasons: set[str] = set()
        self._sleeping = False

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
        self._queue_drops = 0

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

        # Callback when device list or defaults change — engine sets this to push SSE
        self.on_devices_updated: Callable[[], None] | None = None

        # Track when preferred (fixed) devices are temporarily unavailable
        self._input_device_missing = False
        self._output_device_missing = False

        # Circuit breaker: timestamps of recent reconnect attempts
        self._reconnect_timestamps: list[float] = []

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
        import time as _time

        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._on_max_speech = on_max_speech
        self._on_partial_audio = on_partial_audio
        self._on_vad_loading = on_vad_loading

        # Create audio capture — prefer top-level input_device over advanced.device
        device = self._config.input_device or self._config.advanced.device
        _t0 = _time.monotonic()
        self._audio = AudioCapture(
            sample_rate=self._config.advanced.sample_rate,
            channels=self._config.advanced.channels,
            device=device,
        )
        logger.info("AudioCapture init: %.1fs", _time.monotonic() - _t0)

        # Create device monitor (detects OS-level device changes before PortAudio crashes)
        from dictare.audio.device_monitor import create_device_monitor

        _t0 = _time.monotonic()
        self._device_monitor = create_device_monitor(
            on_device_change=self._on_device_change,
        )
        logger.info("DeviceMonitor init: %.1fs", _time.monotonic() - _t0)

        # Notify VAD loading start
        if self._on_vad_loading:
            self._on_vad_loading()

        # Create VAD components
        from dictare.audio.vad import SileroVAD, StreamingVAD

        self._vad = SileroVAD(
            threshold=0.5,
            min_silence_ms=self._config.silence_ms,
            min_speech_ms=self._config.advanced.min_speech_ms,
        )
        # Pre-load the model now (headless mode skips progress indicator)
        _t0 = _time.monotonic()
        self._vad._load_model(with_indicator=not headless, headless=headless)
        logger.info("VAD model load (onnxruntime): %.1fs", _time.monotonic() - _t0)

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
        from dictare.audio.beep import set_audio_control_executor

        set_audio_control_executor(self._execute_audio_lifecycle)
        self._control.execute("start_input", self._start_streaming_owned)
        if self._device_monitor:
            self._device_monitor.start()

    def _start_streaming_owned(self) -> None:
        """Open the input stream on the audio control owner thread."""
        if self._audio:
            self._audio.start_streaming(self.on_audio_chunk)
            if not self._audio.wait_for_audio(timeout_s=2.0):
                logger.error("Initial input stream opened but delivered no audio callbacks")
                self._audio.stop_streaming()
                self._audio = None
                raise RuntimeError("Initial input stream delivered no audio callbacks")

    def _execute_audio_lifecycle(self, label: str, action: Callable[[], Any]) -> Any:
        """Route feedback playback through the owner and suppress it while asleep."""
        return self._control.execute(
            label,
            lambda: None if self._sleeping and label == "play_output" else action(),
        )

    @staticmethod
    def _stop_audio_output_owned() -> None:
        """Stop feedback output, poisoning only when the native call times out."""
        from dictare.audio.beep import stop_portaudio_output

        try:
            stop_portaudio_output()
        except PortAudioCallTimeoutError:
            raise
        except Exception:
            logger.warning("Failed to stop feedback output before audio recovery", exc_info=True)

    def stop_streaming(self) -> None:
        """Stop audio streaming."""
        self._control.execute("stop_input", self._stop_streaming_owned)

    def _stop_streaming_owned(self) -> None:
        """Stop the input stream on the audio control owner thread."""
        if self._audio:
            if self._audio.is_recording():
                self._audio.stop_recording()
            self._audio.stop_streaming()

    def _close_audio_owned(self) -> None:
        """Close output and input lifecycle resources on the owner thread."""
        self._stop_audio_output_owned()
        self._stop_streaming_owned()

    def _on_device_change(self, reason: str) -> None:
        """Handle OS-level device change notification.

        Called from CoreAudio thread (macOS) or polling thread (Linux).
        Must be fast and safe for any thread.

        Policy:
        1. Output-default changes only reset beep output and notify the UI.
           They must not restart input capture/VAD.
        2. Input/default list/wake changes reinit PortAudio, because they can
           invalidate cached device data and active input streams.
        3. Device-list changes check if fixed devices disappeared or returned.
        4. Input-affecting changes restart the input stream after reinit.
        5. Always notify UI via _on_devices_updated.
        """
        logger.info("Device change queued: reason=%s", reason)
        with self._device_change_lock:
            self._device_change_reasons.add(reason)
        try:
            queued = self._control.request(
                "device_change",
                self._process_device_changes_owned,
                coalesce_key="device_change",
            )
            if not queued:
                logger.debug("Device change coalesced: reason=%s", reason)
        except (AudioControlClosedError, AudioControlPoisonedError):
            logger.debug("Device change ignored after audio control stopped")

    def _process_device_changes_owned(self) -> None:
        """Drain and recover coalesced device events on the owner thread."""
        with self._device_change_lock:
            reasons = set(self._device_change_reasons)
            self._device_change_reasons.clear()
        if not reasons:
            return

        self._handle_device_changes_owned(reasons)

    def _handle_device_changes_owned(self, reasons: set[str]) -> None:
        """Apply one recovery transaction for a coalesced device-change burst."""
        from dictare.audio.device_monitor import (
            REASON_DEFAULT_OUTPUT,
            REASON_SLEEP,
            REASON_WAKE,
        )

        logger.info("Device change recovery: reasons=%s", sorted(reasons))

        configured_input = self._config.input_device or ""
        configured_output = self._config.output_device or ""

        # Quiesce before the laptop sleeps. Do not terminate/reinitialize
        # PortAudio while the hardware graph is being suspended; wake owns the
        # subsequent full recovery transaction.
        if REASON_SLEEP in reasons:
            self._sleeping = True
        if self._sleeping and REASON_WAKE not in reasons:
            if REASON_DEFAULT_OUTPUT in reasons and not configured_output:
                self.reset_audio_output("")
            self._stop_audio_output_owned()
            if self._audio:
                self._audio.emergency_abort()
                self._audio = None
            logger.info("Audio quiesced for system sleep")
            if self.on_devices_updated:
                self.on_devices_updated()
            return

        # If sleep and wake collapsed into the same burst, wake wins and the
        # regular input-affecting recovery below rebuilds the complete graph.
        reasons.discard(REASON_SLEEP)
        if REASON_WAKE in reasons:
            self._sleeping = False
            logger.info("Audio recovery requested after system wake")

        # Output-only default switches should be seamless. Reinitializing
        # PortAudio here kills the active input stream and resets VAD, which
        # feels like an engine restart even though no restart command was sent.
        if REASON_DEFAULT_OUTPUT in reasons and not configured_output:
            logger.info("Default output changed, resetting audio output")
            self.reset_audio_output("")

        input_affecting = reasons - {REASON_DEFAULT_OUTPUT}
        if not input_affecting:
            if self.on_devices_updated:
                self.on_devices_updated()
            return

        import sounddevice as sd

        # Reinit PortAudio to refresh cached device lists and defaults.
        # sd.query_devices() and sd.default.device return stale data without this.
        # Reinit kills any active input stream, so we restart it below.
        # _audio may be None after a failed reconnect (e.g. wake from sleep).
        self._stop_audio_output_owned()
        if self._audio:
            self._audio.emergency_abort()
            self._audio = None
        self._reinit_portaudio(sd, timeout_s=3.0)

        # --- Check fixed devices: disappearance + auto-reconnect ---
        # Config is the user's PREFERENCE — never modified by system.
        if configured_input or configured_output:
            device_names = {d["name"] for d in AudioCapture.list_devices()}
            output_names = {d["name"] for d in AudioCapture.list_output_devices()}

            if configured_input:
                gone = configured_input not in device_names
                if gone and not self._input_device_missing:
                    logger.warning(
                        "Preferred input %r unavailable — using default",
                        configured_input,
                    )
                    self._input_device_missing = True
                elif not gone and self._input_device_missing:
                    logger.info(
                        "Preferred input %r is back — reconnecting",
                        configured_input,
                    )
                    self._input_device_missing = False

            if configured_output:
                gone = configured_output not in output_names
                if gone and not self._output_device_missing:
                    logger.warning(
                        "Preferred output %r unavailable — using default",
                        configured_output,
                    )
                    self._output_device_missing = True
                    self.reset_audio_output("")  # fall back to default
                elif not gone and self._output_device_missing:
                    logger.info(
                        "Preferred output %r is back — reconnecting",
                        configured_output,
                    )
                    self._output_device_missing = False
                    self.reset_audio_output(configured_output)

        # Restart input stream (always needed after PortAudio reinit)
        # _restart_input_stream reads config.input_device — AudioCapture falls
        # back to default when the configured device is gone.
        self._restart_input_stream()

        # Notify UI so dropdowns update with fresh device data
        if self.on_devices_updated:
            self.on_devices_updated()

    def reset_audio_input(self) -> None:
        """Reset audio input stream to current config/default device.

        Lighter than reconnect() — no circuit breaker, no retries, single attempt.
        Stops stream → reinit PortAudio → new AudioCapture → start stream → reset VAD.
        """
        self._control.execute("reset_input", self._reset_audio_input_owned)

    def _reset_audio_input_owned(self) -> None:
        """Reset input from the audio control owner thread."""
        import sounddevice as sd

        logger.info("Resetting audio input")

        # Stop old stream
        self._stop_audio_output_owned()
        if self._audio:
            self._audio.emergency_abort()
            self._audio = None

        # Reinit PortAudio to pick up new device list
        self._reinit_portaudio(sd, timeout_s=3.0)

        # Restart with fresh PortAudio session
        self._restart_input_stream()

    def _restart_input_stream(self) -> None:
        """Start a fresh input stream after PortAudio reinit.

        Creates a new AudioCapture with current config and starts streaming.
        Call this after _reinit_portaudio() to resume audio capture.
        """
        device = self._config.input_device or self._config.advanced.device
        try:
            self._audio = AudioCapture(
                sample_rate=self._config.advanced.sample_rate,
                channels=self._config.advanced.channels,
                device=device,
            )
            self._audio.start_streaming(self.on_audio_chunk)
            if not self._audio.wait_for_audio(timeout_s=2.0):
                logger.warning("Restarted input stream delivered no audio callbacks")
                self._audio.stop_streaming()
                self._audio = None
                return
            self.reset_vad()
            logger.info(
                "Input stream recovery verified by audio callback, device=%r",
                device or "(default)",
            )
        except PortAudioCallTimeoutError:
            self._audio = None
            raise
        except Exception:
            logger.exception("Failed to restart input stream")
            self._audio = None

    def reset_audio_output(self, device: str) -> None:
        """Reset audio output device for beep playback.

        Args:
            device: Device name or empty string for system default.
        """
        from dictare.audio.beep import set_output_device
        set_output_device(device)
        logger.info("Audio output device set to %r", device or "(default)")

    def get_actual_devices(self) -> dict:
        """Return the actual devices currently in use (for UI 'in use' label)."""
        import sounddevice as sd

        input_name = None
        if self._audio and self._audio._stream:
            try:
                info = sd.query_devices(self._audio._stream.device, "input")
                input_name = info["name"]
            except Exception:
                pass
        if input_name is None:
            default = AudioCapture.get_default_device()
            input_name = default["name"] if default else None

        output_name = None
        from dictare.audio.beep import _output_device
        if _output_device:
            # Verify configured device still exists; if not, show actual default
            try:
                available = AudioCapture.list_output_devices()
                exists = any(d["name"] == _output_device for d in available)
            except Exception:
                exists = False
            if exists:
                output_name = str(_output_device)
            else:
                default = AudioCapture.get_default_output_device()
                output_name = default["name"] if default else None
        else:
            default = AudioCapture.get_default_output_device()
            output_name = default["name"] if default else None

        return {"input": input_name, "output": output_name}

    def close(self) -> None:
        """Clean up all resources.

        Call this on shutdown to release ONNX session resources
        and avoid semaphore leak warnings.
        """
        # Stop device monitor first
        if self._device_monitor:
            self._device_monitor.stop()
            self._device_monitor = None
        self._sleeping = True

        # A native timeout poisons the process. Never issue another PortAudio
        # call from cleanup; the outer launcher will replace the process.
        if not self._control.poisoned:
            try:
                self._control.execute("close_audio", self._close_audio_owned)
            except Exception:
                logger.exception("Failed to stop audio during close")
        else:
            logger.warning(
                "Skipping PortAudio cleanup in poisoned process: %s",
                self._control.poisoned_reason,
            )
        self._control.shutdown()
        from dictare.audio.beep import set_audio_control_executor

        set_audio_control_executor(None)

        # Acquire lock to ensure no callback is currently using VAD
        # This synchronizes with on_audio_chunk() which also holds this lock
        with self._vad_lock:
            self._streaming_vad = None

        # Now close the VAD (safe because callbacks can't use it anymore)
        if self._vad:
            self._vad.close()
            self._vad = None

    def on_audio_chunk(self, chunk: Any) -> None:
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

    @property
    def reconnect_reason(self) -> str | None:
        """Why audio needs reconnection, or None if healthy."""
        if self._audio is None:
            # Audio object destroyed by a previous failed reconnect —
            # must try again (e.g. after wake from sleep).
            return "audio_dead"
        return self._audio.reconnect_reason

    def reconnect(self, on_chunk_callback: Callable[[Any], None]) -> bool:
        """Attempt to reconnect audio device with circuit breaker.

        Circuit breaker: stops after _MAX_RECONNECTS in _RECONNECT_WINDOW_S
        to prevent reconnect storms (e.g. flaky USB hub).

        Args:
            on_chunk_callback: Callback for audio chunks after reconnection

        Returns:
            True if reconnection succeeded, False if failed or circuit breaker tripped
        """
        return bool(
            self._control.execute(
                "reconnect_input",
                lambda: self._reconnect_owned(on_chunk_callback),
            )
        )

    def _reconnect_owned(self, on_chunk_callback: Callable[[Any], None]) -> bool:
        """Perform a full reconnect transaction on the owner thread."""
        import sounddevice as sd

        # Circuit breaker: too many reconnects in window?
        now = time.monotonic()
        self._reconnect_timestamps = [
            t for t in self._reconnect_timestamps
            if now - t < self._RECONNECT_WINDOW_S
        ]
        if len(self._reconnect_timestamps) >= self._MAX_RECONNECTS:
            logger.error(
                "Circuit breaker: %d reconnects in %ds — stopping reconnect attempts",
                self._MAX_RECONNECTS,
                int(self._RECONNECT_WINDOW_S),
            )
            return False
        self._reconnect_timestamps.append(now)

        # Stop device monitor during reconnection
        if self._device_monitor:
            self._device_monitor.stop()

        # Abort old stream immediately (no lock, no waiting for callbacks)
        if self._audio:
            self._audio.emergency_abort()
            self._audio = None

        # Determine target device: configured or system default
        configured_device = self._config.input_device or None

        # Retry with fresh AudioCapture object
        for attempt in range(5):
            if self._on_reconnect_attempt:
                self._on_reconnect_attempt(attempt + 1)
            time.sleep(1.0)

            # On last attempt, fallback to system default even if device is configured
            use_device = configured_device if attempt < 4 else None
            logger.info(
                "Reconnect attempt %d/5 with device=%r",
                attempt + 1, use_device,
            )

            try:
                # Skip Pa_Terminate on first attempt — avoids deadlock when
                # CoreAudio is still processing the device change
                if attempt > 0:
                    self._stop_audio_output_owned()
                    self._reinit_portaudio(sd, timeout_s=3.0)

                self._audio = AudioCapture(
                    sample_rate=self._config.advanced.sample_rate,
                    channels=self._config.advanced.channels,
                    device=use_device,
                )
                self._audio.start_streaming(on_chunk_callback)

                # Verify audio is actually flowing (not a zombie stream)
                if not self._audio.wait_for_audio(timeout_s=2.0):
                    logger.warning("Reconnect attempt %d/5: no audio data — zombie stream", attempt + 1)
                    self._audio.stop_streaming()
                    self._audio = None
                    continue

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

                # Cooldown: let the stream stabilize before returning
                time.sleep(self._RECONNECT_COOLDOWN_S)
                return True
            except PortAudioCallTimeoutError:
                self._audio = None
                raise
            except Exception as exc:
                logger.warning("Reconnect attempt %d/5 failed: %s", attempt + 1, exc)
                self._audio = None
        logger.error("All reconnect attempts exhausted")
        return False

    @staticmethod
    def _reinit_portaudio(sd: Any, timeout_s: float = 3.0) -> None:
        """Reinitialize PortAudio with a timeout.

        Pa_Terminate() can deadlock when CoreAudio is in a corrupted state.
        A timeout poisons the process; callers must not continue with another
        PortAudio lifecycle call in the same address space.
        """
        def _do_reinit() -> None:
            try:
                sd._terminate()
            finally:
                sd._initialize()

        _run_with_timeout(_do_reinit, timeout_s=timeout_s, label="reinit")

    @property
    def audio_control_poisoned(self) -> bool:
        """Whether native audio timed out in this process."""
        return self._control.poisoned

    def wait_for_audio_control(self) -> None:
        """Wait for already queued audio-control work (primarily for tests)."""
        self._control.barrier()

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
            self._queue_drops += 1
            logger.warning(
                "Audio queue full — dropping oldest utterance (%d dropped total)",
                self._queue_drops,
            )
            try:
                self._audio_queue.get_nowait()
            except Empty:
                pass
            try:
                self._audio_queue.put_nowait(audio_data)
            except Full:
                # Still full, drop this audio
                self._queue_drops += 1
                logger.warning(
                    "Audio queue still full — dropping incoming utterance "
                    "(%d dropped total)",
                    self._queue_drops,
                )

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
    def is_speaking(self) -> bool:
        """Whether VAD currently detects speech."""
        with self._vad_lock:
            return self._streaming_vad is not None and self._streaming_vad._is_speaking

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
