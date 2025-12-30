"""Audio capture using sounddevice."""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Callable

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from numpy.typing import NDArray


class AudioCapture:
    """Records audio from microphone using sounddevice.

    Uses callback-based streaming for low latency.
    """

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

    def _audio_callback(
        self,
        indata: NDArray[np.float32],
        frames: int,
        time_info: dict,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback for sounddevice stream."""
        if status:
            print(f"Audio status: {status}")
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
                device=self.device,
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

    def start_streaming(self, callback: Callable[["NDArray[np.float32]"], None]) -> None:
        """Start continuous audio streaming with callback.

        Args:
            callback: Called for each audio chunk (512 samples for VAD).
        """
        with self._lock:
            if self._stream is not None:
                return

            self._streaming_callback = callback
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=self.device,
                dtype=self.dtype,
                blocksize=512,  # Match VAD chunk size
                callback=self._streaming_audio_callback,
            )
            self._stream.start()

    def _streaming_audio_callback(
        self,
        indata: NDArray[np.float32],
        frames: int,
        time_info: dict,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback for streaming mode."""
        if hasattr(self, "_streaming_callback") and self._streaming_callback:
            self._streaming_callback(indata.flatten().copy())

    def stop_streaming(self) -> None:
        """Stop continuous audio streaming."""
        with self._lock:
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
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
            return None
