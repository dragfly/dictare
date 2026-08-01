"""Audio capture using sounddevice."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class PortAudioCallTimeoutError(TimeoutError):
    """A PortAudio call outlived its deadline and may still own native state."""


def _abort_close_stream(stream: Any) -> None:
    """Best-effort abort + close of a PortAudio stream, swallowing errors."""
    if stream is None:
        return
    try:
        stream.abort()
    except Exception:
        pass
    try:
        stream.close()
    except Exception:
        pass


def _run_with_timeout(
    fn: Callable[[], Any],
    timeout_s: float,
    label: str,
) -> Any:
    """Run a blocking PortAudio call with a hard timeout.

    PortAudio/CoreAudio calls (open, start, stop, close, abort) can block
    indefinitely after a device error on macOS (e.g. error -50 following a
    device change). Running them in a daemon thread and abandoning them on
    timeout keeps the caller — in particular the audio reconnect loop — from
    wedging forever while holding a lock.

    This mirrors the watchdog already used for ``Pa_Terminate`` in
    ``AudioManager._reinit_portaudio`` so every blocking call is bounded the
    same way.

    Returns the call's result, or raises ``PortAudioCallTimeoutError`` if it does
    not finish within ``timeout_s``. The caller must replace the process after
    a timeout; no later PortAudio cleanup is safe in the same process.
    """
    box: dict[str, Any] = {}
    done = threading.Event()

    def _runner() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 — re-raised in caller thread
            box["error"] = exc
        finally:
            done.set()

    threading.Thread(target=_runner, daemon=True, name=f"pa-{label}").start()

    if done.wait(timeout=timeout_s):
        if "error" in box:
            raise box["error"]
        return box.get("result")

    logger.warning(
        "PortAudio %s timed out after %.1fs — abandoning call", label, timeout_s
    )
    raise PortAudioCallTimeoutError(f"PortAudio {label} timed out after {timeout_s}s")


class AudioCapture:
    """Records audio from microphone using sounddevice.

    Uses callback-based streaming for low latency.
    Automatically reconnects if audio device is unplugged.
    """

    # Require N consecutive PortAudio errors before flagging reconnect.
    # A single transient error (e.g. brief USB glitch) shouldn't trigger
    # a full reconnect cycle.
    _CALLBACK_ERROR_THRESHOLD = 3

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device: str | int | None = None,
        dtype: str = "float32",
    ) -> None:
        """Initialize audio capture.

        Args:
            sample_rate: Sample rate in Hz (default 16000 for Whisper).
            channels: Number of audio channels (default 1 for mono).
            device: Audio device name or index (None for default).
            dtype: Audio data type.
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self.dtype = dtype
        self._buffer: queue.Queue[NDArray[np.float32]] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()
        self._needs_reconnect = False
        self._callback_error_count = 0  # consecutive PortAudio errors
        self._streaming_callback: Callable[[Any], None] | None = None
        self._last_callback_time: float = 0.0  # monotonic timestamp of last callback

    def _audio_callback(
        self,
        indata: NDArray[np.float32],
        _frames: int,
        _time_info: dict,
        _status: sd.CallbackFlags,
    ) -> None:
        """Callback for sounddevice stream."""
        if self._recording:
            self._buffer.put(indata.copy())

    def start_recording(self) -> None:
        """Start recording audio."""
        with self._lock:
            if self._recording:
                return

            self._buffer = queue.Queue()
            self._recording = True

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=self.device or None,  # Empty string -> None (use default)
                dtype=self.dtype,
                callback=self._audio_callback,
            )
            self._stream.start()

    def stop_recording(self) -> NDArray[np.float32]:
        """Stop recording and return audio data.

        Returns:
            Numpy array of audio samples (float32, mono).
        """
        with self._lock:
            self._recording = False

            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            # Collect all buffered audio
            chunks: list[NDArray[np.float32]] = []
            while not self._buffer.empty():
                try:
                    chunks.append(self._buffer.get_nowait())
                except queue.Empty:
                    break

            if chunks:
                audio = np.concatenate(chunks, axis=0).flatten()
                return audio.astype(np.float32)

            return np.array([], dtype=np.float32)

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._recording

    @staticmethod
    def list_devices() -> list[dict]:
        """List available audio input devices.

        Returns:
            List of device info dictionaries.
        """
        devices = sd.query_devices()
        input_devices = []

        for i, device in enumerate(devices):  # type: ignore
            if device["max_input_channels"] > 0:  # type: ignore
                input_devices.append(
                    {
                        "index": i,
                        "name": device["name"],  # type: ignore
                        "channels": device["max_input_channels"],  # type: ignore
                        "sample_rate": device["default_samplerate"],  # type: ignore
                    }
                )

        return input_devices

    @staticmethod
    def list_output_devices() -> list[dict]:
        """List available audio output devices.

        Returns:
            List of device info dictionaries.
        """
        devices = sd.query_devices()
        output_devices = []

        for i, device in enumerate(devices):  # type: ignore
            if device["max_output_channels"] > 0:  # type: ignore
                output_devices.append(
                    {
                        "index": i,
                        "name": device["name"],  # type: ignore
                        "channels": device["max_output_channels"],  # type: ignore
                        "sample_rate": device["default_samplerate"],  # type: ignore
                    }
                )

        return output_devices

    @staticmethod
    def get_default_output_device() -> dict | None:
        """Get default output device info.

        Returns:
            Device info dictionary or None if no default.
        """
        try:
            default_idx = sd.default.device[1]  # Output device
            if default_idx is None:
                return None

            device = sd.query_devices(default_idx)
            return {
                "index": default_idx,
                "name": device["name"],  # type: ignore
                "channels": device["max_output_channels"],  # type: ignore
                "sample_rate": device["default_samplerate"],  # type: ignore
            }
        except Exception:
            logger.debug("Failed to query output device", exc_info=True)
            return None

    def start_streaming(self, callback: Callable[[NDArray[np.float32]], None]) -> None:
        """Start continuous audio streaming with callback.

        Args:
            callback: Called for each audio chunk (512 samples for VAD).
        """
        with self._lock:
            if self._stream is not None:
                return

            self._streaming_callback = callback
            self._last_callback_time = time.monotonic()

            def _open() -> sd.InputStream:
                stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    device=self.device or None,  # Empty string -> None (use default)
                    dtype=self.dtype,
                    blocksize=512,  # Match VAD chunk size
                    callback=self._streaming_audio_callback,
                )
                stream.start()
                return stream

            # Bound the open/start: a corrupted CoreAudio state can make these
            # block forever, which would wedge the reconnect loop. A timeout
            # poisons the process, so the abandoned call is never touched again.
            try:
                self._stream = _run_with_timeout(
                    _open, timeout_s=5.0, label="open"
                )
            except Exception:
                self._streaming_callback = None
                raise

    def _streaming_audio_callback(
        self,
        indata: NDArray[np.float32],
        _frames: int,
        _time_info: dict,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback for streaming mode."""
        if status:
            if status.input_overflow:
                # Input overflow is benign — CPU spike, brief lag, etc.
                # Process the chunk anyway (data is valid, just slightly late).
                pass
            else:
                # Real device error — count consecutive failures before reconnect
                self._callback_error_count += 1
                if self._callback_error_count >= self._CALLBACK_ERROR_THRESHOLD:
                    logger.warning(
                        "PortAudio: %d consecutive errors, flagging reconnect",
                        self._callback_error_count,
                    )
                    self._needs_reconnect = True
                return
        self._callback_error_count = 0  # reset on success
        self._last_callback_time = time.monotonic()
        if self._streaming_callback is not None:
            self._streaming_callback(indata.flatten().copy())

    def stop_streaming(self) -> None:
        """Stop continuous audio streaming."""
        with self._lock:
            if self._stream:
                stream = self._stream
                self._stream = None
                # Bound stop/close: like open, these can hang on a dead device.
                _run_with_timeout(
                    lambda: (stream.stop(), stream.close()),
                    timeout_s=3.0,
                    label="stop",
                )
            self._streaming_callback = None

    @staticmethod
    def get_default_device() -> dict | None:
        """Get default input device info.

        Returns:
            Device info dictionary or None if no default.
        """
        try:
            default_idx = sd.default.device[0]  # Input device
            if default_idx is None:
                return None

            device = sd.query_devices(default_idx)
            return {
                "index": default_idx,
                "name": device["name"],  # type: ignore
                "channels": device["max_input_channels"],  # type: ignore
                "sample_rate": device["default_samplerate"],  # type: ignore
            }
        except Exception:
            logger.debug("Failed to query default input device", exc_info=True)
            return None

    def emergency_abort(self) -> None:
        """Abort and close the stream from the audio control owner."""
        self._needs_reconnect = True
        stream = self._stream  # Atomic reference read
        self._stream = None
        if stream is not None:
            _run_with_timeout(
                lambda: _abort_close_stream(stream),
                timeout_s=3.0,
                label="abort",
            )

    @property
    def reconnect_reason(self) -> str | None:
        """Why audio needs reconnection, or None if healthy.

        Unifies three failure modes:
        - "callback_error": PortAudio reported N consecutive errors
        - "stream_inactive": stream.active is False (device unplugged)
        - "stream_stale": stream reports active but no data for 3s (zombie)
        """
        if self._needs_reconnect:
            return "callback_error"
        if self._stream is not None and not self._stream.active:
            return "stream_inactive"
        if (
            self._stream is not None
            and self._stream.active
            and (time.monotonic() - self._last_callback_time) > 3.0
        ):
            return "stream_stale"
        return None

    def wait_for_audio(self, timeout_s: float = 2.0) -> bool:
        """Wait for at least one audio callback after stream start.

        Args:
            timeout_s: Maximum seconds to wait.

        Returns:
            True if data arrived, False if timed out (zombie stream).
        """
        start = time.monotonic()
        baseline = self._last_callback_time
        while (time.monotonic() - start) < timeout_s:
            if self._last_callback_time > baseline:
                return True
            time.sleep(0.05)
        return False
