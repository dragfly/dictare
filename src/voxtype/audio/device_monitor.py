"""Cross-platform audio device change monitor.

Detects audio device connect/disconnect events at the OS level, BEFORE
PortAudio's IOThread can crash with an assertion failure (SIGABRT).

macOS: CoreAudio AudioObjectAddPropertyListener via ctypes.
Linux: Polling sounddevice.query_devices() default device index.
"""

from __future__ import annotations

import logging
import sys
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

class DeviceMonitor(ABC):
    """Monitors OS-level audio device changes.

    Detects device connect/disconnect events BEFORE PortAudio's IOThread
    reacts, preventing SIGABRT from assertion failures in AudioIOProc.
    """

    def __init__(self, on_device_change: Callable[[], None]) -> None:
        self._on_device_change = on_device_change
        self._running = False

    @abstractmethod
    def start(self) -> None:
        """Start monitoring. Non-blocking."""

    @abstractmethod
    def stop(self) -> None:
        """Stop monitoring and clean up resources."""

    @property
    def running(self) -> bool:
        return self._running

class CoreAudioDeviceMonitor(DeviceMonitor):
    """macOS device monitor using CoreAudio property listeners.

    Listens for kAudioHardwarePropertyDefaultInputDevice changes on
    kAudioObjectSystemObject. The callback fires on CoreAudio's internal
    thread, BEFORE PortAudio's IOThread sees the stale device.

    Uses ctypes — no pyobjc dependency.
    """

    def __init__(self, on_device_change: Callable[[], None]) -> None:
        super().__init__(on_device_change)
        self._listener_installed = False
        self._callback_ref: Any = None  # prevent GC of ctypes callback
        self._property_address: Any = None
        self._core_audio: Any = None

    def start(self) -> None:
        if self._running:
            return
        self._install_listener()
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._remove_listener()
        self._running = False

    def _install_listener(self) -> None:
        """Install CoreAudio property listener via ctypes."""
        import ctypes
        from ctypes import CFUNCTYPE, POINTER, Structure, c_int32, c_uint32, c_void_p

        core_audio = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreAudio.framework/CoreAudio"
        )

        class AudioObjectPropertyAddress(Structure):
            _fields_ = [
                ("mSelector", c_uint32),
                ("mScope", c_uint32),
                ("mElement", c_uint32),
            ]

        # Callback: OSStatus (*)(AudioObjectID, UInt32, const AudioObjectPropertyAddress*, void*)
        listener_proc_type = CFUNCTYPE(
            c_int32, c_uint32, c_uint32,
            POINTER(AudioObjectPropertyAddress), c_void_p,
        )

        def _on_property_change(
            _obj_id: int, _num: int, _addrs: Any, _data: Any,
        ) -> int:
            """CoreAudio callback — runs on CoreAudio's internal thread."""
            try:
                self._on_device_change()
            except Exception:
                pass  # Never let exceptions escape into C
            return 0  # noErr

        # Keep reference to prevent garbage collection
        self._callback_ref = listener_proc_type(_on_property_change)

        # FourCC constants
        selector = int.from_bytes(b"dIn ", "big")  # kAudioHardwarePropertyDefaultInputDevice
        scope = int.from_bytes(b"glob", "big")  # kAudioObjectPropertyScopeGlobal
        element = 0  # kAudioObjectPropertyElementMain

        self._property_address = AudioObjectPropertyAddress(selector, scope, element)
        self._core_audio = core_audio

        status = core_audio.AudioObjectAddPropertyListener(
            c_uint32(1),  # kAudioObjectSystemObject
            ctypes.byref(self._property_address),
            self._callback_ref,
            None,
        )
        if status != 0:
            logger.warning("Failed to install CoreAudio device listener: OSStatus %d", status)
        else:
            self._listener_installed = True
            logger.debug("CoreAudio device monitor installed")

    def _remove_listener(self) -> None:
        """Remove CoreAudio property listener."""
        if not self._listener_installed:
            return
        try:
            import ctypes

            self._core_audio.AudioObjectRemovePropertyListener(
                ctypes.c_uint32(1),
                ctypes.byref(self._property_address),
                self._callback_ref,
                None,
            )
            self._listener_installed = False
            logger.debug("CoreAudio device monitor removed")
        except Exception:
            logger.debug("Failed to remove CoreAudio listener", exc_info=True)

class PollingDeviceMonitor(DeviceMonitor):
    """Fallback device monitor using periodic device list polling.

    Polls sounddevice default input device every 2 seconds and fires
    the callback if the default device index changes. Sufficient for
    Linux where PulseAudio/PipeWire handle re-routing more gracefully.
    """

    POLL_INTERVAL = 2.0

    def __init__(self, on_device_change: Callable[[], None]) -> None:
        super().__init__(on_device_change)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_device: int | None = None

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._last_device = self._get_default_input_device()
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="voxtype-device-poll",
        )
        self._thread.start()
        self._running = True
        logger.debug("Polling device monitor started")

    def stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._running = False
        logger.debug("Polling device monitor stopped")

    def _poll_loop(self) -> None:
        """Poll for device changes."""
        while not self._stop_event.wait(timeout=self.POLL_INTERVAL):
            try:
                current = self._get_default_input_device()
                if current != self._last_device:
                    logger.debug(
                        "Default input device changed: %s -> %s",
                        self._last_device, current,
                    )
                    self._last_device = current
                    self._on_device_change()
            except Exception:
                # query_devices() can fail if PortAudio is in a bad state
                logger.debug("Device poll failed", exc_info=True)
                self._on_device_change()

    @staticmethod
    def _get_default_input_device() -> int | None:
        """Get current default input device index."""
        try:
            import sounddevice as sd

            idx = sd.default.device[0]
            return idx
        except Exception:
            return None

def create_device_monitor(on_device_change: Callable[[], None]) -> DeviceMonitor:
    """Create platform-appropriate device monitor.

    Returns CoreAudioDeviceMonitor on macOS, PollingDeviceMonitor on Linux.
    """
    if sys.platform == "darwin":
        return CoreAudioDeviceMonitor(on_device_change)
    return PollingDeviceMonitor(on_device_change)
