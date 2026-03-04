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

# Reason strings passed to the callback
REASON_DEFAULT_INPUT = "default_input_changed"
REASON_DEFAULT_OUTPUT = "default_output_changed"
REASON_DEVICES = "devices_changed"
REASON_WAKE = "system_wake"

class DeviceMonitor(ABC):
    """Monitors OS-level audio device changes.

    Detects device connect/disconnect events BEFORE PortAudio's IOThread
    reacts, preventing SIGABRT from assertion failures in AudioIOProc.
    """

    def __init__(self, on_device_change: Callable[[str], None]) -> None:
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

    Listens for:
    - kAudioHardwarePropertyDefaultInputDevice  (b"dIn ") — default input changed
    - kAudioHardwarePropertyDefaultOutputDevice (b"dOut") — default output changed
    - kAudioHardwarePropertyDevices             (b"dev#") — device list changed

    Callbacks fire on CoreAudio's internal thread, BEFORE PortAudio's IOThread
    sees the stale device.

    Uses ctypes — no pyobjc dependency.
    """

    def __init__(self, on_device_change: Callable[[str], None]) -> None:
        super().__init__(on_device_change)
        self._listeners_installed = False
        self._callback_refs: list[Any] = []  # prevent GC of ctypes callbacks
        self._property_addresses: list[Any] = []
        self._core_audio: Any = None
        self._wake_observer: Any = None

    def start(self) -> None:
        if self._running:
            return
        self._install_listeners()
        self._install_wake_observer()
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._remove_listeners()
        self._remove_wake_observer()
        self._running = False

    def _install_listeners(self) -> None:
        """Install CoreAudio property listeners via ctypes."""
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

        scope = int.from_bytes(b"glob", "big")  # kAudioObjectPropertyScopeGlobal
        element = 0  # kAudioObjectPropertyElementMain

        # (FourCC selector, reason string)
        properties = [
            (b"dIn ", REASON_DEFAULT_INPUT),
            (b"dOut", REASON_DEFAULT_OUTPUT),
            (b"dev#", REASON_DEVICES),
        ]

        self._core_audio = core_audio

        for fourcc, reason in properties:
            def _make_callback(r: str) -> Any:
                def _on_property_change(
                    _obj_id: int, _num: int, _addrs: Any, _data: Any,
                ) -> int:
                    """CoreAudio callback — runs on CoreAudio's internal thread."""
                    try:
                        self._on_device_change(r)
                    except Exception:
                        pass  # Never let exceptions escape into C
                    return 0  # noErr
                return listener_proc_type(_on_property_change)

            callback_ref = _make_callback(reason)
            self._callback_refs.append(callback_ref)

            selector = int.from_bytes(fourcc, "big")
            addr = AudioObjectPropertyAddress(selector, scope, element)
            self._property_addresses.append(addr)

            status = core_audio.AudioObjectAddPropertyListener(
                c_uint32(1),  # kAudioObjectSystemObject
                ctypes.byref(addr),
                callback_ref,
                None,
            )
            if status != 0:
                logger.warning(
                    "Failed to install CoreAudio listener %s: OSStatus %d",
                    fourcc.decode(), status,
                )
            else:
                logger.debug("CoreAudio listener installed: %s", fourcc.decode())

        self._listeners_installed = True
        logger.debug("CoreAudio device monitor installed (%d listeners)", len(properties))

    def _install_wake_observer(self) -> None:
        """Listen for NSWorkspaceDidWakeNotification (system wake from sleep).

        Uses PyObjC (bundled with macOS Python and available via pyobjc-framework-Cocoa).
        Runs a dedicated CFRunLoop thread to receive the notification.
        """
        try:
            from AppKit import NSWorkspace  # type: ignore[import-untyped]
        except ImportError:
            logger.debug("PyObjC not available — wake observer skipped")
            return

        try:
            def _on_wake(_notification: Any) -> None:
                logger.info("System wake detected (NSWorkspaceDidWakeNotification)")
                try:
                    self._on_device_change(REASON_WAKE)
                except Exception:
                    pass

            center = NSWorkspace.sharedWorkspace().notificationCenter()
            center.addObserverForName_object_queue_usingBlock_(
                "NSWorkspaceDidWakeNotification",
                None,
                None,  # deliver on posting thread (CoreAudio/AppKit thread)
                _on_wake,
            )
            self._wake_observer = (center, _on_wake)
            logger.debug("macOS wake observer installed")
        except Exception:
            logger.debug("Failed to install wake observer", exc_info=True)

    def _remove_wake_observer(self) -> None:
        """Remove the wake notification observer."""
        if self._wake_observer is None:
            return
        try:
            center, _block = self._wake_observer
            center.removeObserver_(self._wake_observer)
            logger.debug("macOS wake observer removed")
        except Exception:
            logger.debug("Failed to remove wake observer", exc_info=True)
        self._wake_observer = None

    def _remove_listeners(self) -> None:
        """Remove all CoreAudio property listeners."""
        if not self._listeners_installed:
            return
        try:
            import ctypes

            for addr, callback_ref in zip(self._property_addresses, self._callback_refs):
                try:
                    self._core_audio.AudioObjectRemovePropertyListener(
                        ctypes.c_uint32(1),
                        ctypes.byref(addr),
                        callback_ref,
                        None,
                    )
                except Exception:
                    pass
            self._listeners_installed = False
            logger.debug("CoreAudio device monitor removed")
        except Exception:
            logger.debug("Failed to remove CoreAudio listeners", exc_info=True)
        finally:
            self._callback_refs.clear()
            self._property_addresses.clear()

class PollingDeviceMonitor(DeviceMonitor):
    """Fallback device monitor using periodic device list polling.

    Polls sounddevice default input/output device and device count every 2 seconds.
    Fires the callback with a reason string indicating what changed.
    """

    POLL_INTERVAL = 2.0

    def __init__(self, on_device_change: Callable[[str], None]) -> None:
        super().__init__(on_device_change)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_input: int | None = None
        self._last_output: int | None = None
        self._last_count: int = 0

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._last_input, self._last_output, self._last_count = self._snapshot()
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="dictare-device-poll",
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
                cur_in, cur_out, cur_count = self._snapshot()

                if cur_count != self._last_count:
                    logger.debug(
                        "Device count changed: %d -> %d",
                        self._last_count, cur_count,
                    )
                    self._last_input = cur_in
                    self._last_output = cur_out
                    self._last_count = cur_count
                    self._on_device_change(REASON_DEVICES)
                    continue

                if cur_in != self._last_input:
                    logger.debug(
                        "Default input device changed: %s -> %s",
                        self._last_input, cur_in,
                    )
                    self._last_input = cur_in
                    self._on_device_change(REASON_DEFAULT_INPUT)

                if cur_out != self._last_output:
                    logger.debug(
                        "Default output device changed: %s -> %s",
                        self._last_output, cur_out,
                    )
                    self._last_output = cur_out
                    self._on_device_change(REASON_DEFAULT_OUTPUT)

            except Exception:
                # query_devices() can fail if PortAudio is in a bad state
                logger.debug("Device poll failed", exc_info=True)
                self._on_device_change(REASON_DEVICES)

    @staticmethod
    def _snapshot() -> tuple[int | None, int | None, int]:
        """Return (default_input_idx, default_output_idx, device_count)."""
        try:
            import sounddevice as sd

            default = sd.default.device
            count = len(sd.query_devices())
            return default[0], default[1], count
        except Exception:
            return None, None, 0

def create_device_monitor(on_device_change: Callable[[str], None]) -> DeviceMonitor:
    """Create platform-appropriate device monitor.

    Returns CoreAudioDeviceMonitor on macOS, PollingDeviceMonitor on Linux.
    """
    if sys.platform == "darwin":
        return CoreAudioDeviceMonitor(on_device_change)
    return PollingDeviceMonitor(on_device_change)
