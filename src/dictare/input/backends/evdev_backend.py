"""evdev backend for device input (Linux only).

Uses evdev for exclusive device grab on Linux.
This is the preferred backend on Linux.

Requirements:
    pip install evdev
    User must be in 'input' group: sudo usermod -aG input $USER
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from dictare.input.backends.base import DeviceBackend

class EvdevBackend(DeviceBackend):
    """Linux evdev device input with exclusive grab.

    Pro: Exclusive device grab, native Linux support
    Con: Linux only, requires input group membership
    """

    def __init__(self, verbose: bool = False, debounce_ms: int = 300) -> None:
        self._verbose = verbose
        self._debounce_ms = debounce_ms
        self._running = False
        self._device: Any = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_command_time: float = 0
        self._on_command: Callable[[str, dict[str, Any]], None] | None = None
        self._bindings: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "evdev"

    @property
    def supports_grab(self) -> bool:
        return True

    def is_available(self) -> bool:
        """Check if evdev is available."""
        if sys.platform != "linux":
            return False
        try:
            import evdev  # noqa: F401
            return True
        except ImportError:
            return False

    def list_devices(self) -> list[dict]:
        """List evdev input devices."""
        if sys.platform != "linux":
            return []

        try:
            import evdev

            devices = []
            for path in evdev.list_devices():
                try:
                    device = evdev.InputDevice(path)
                    devices.append({
                        "vendor_id": device.info.vendor,
                        "product_id": device.info.product,
                        "manufacturer": "",
                        "product": device.name,
                        "path": path,
                    })
                    device.close()
                except Exception:
                    continue
            return devices
        except ImportError:
            return []

    def start(
        self,
        device_id: str,
        bindings: dict[str, str],
        on_command: Callable[[str, dict], None],
    ) -> bool:
        """Start listening to the evdev device."""
        try:
            import evdev
        except ImportError:
            if self._verbose:
                print("[evdev] evdev not installed")
            return False

        self._bindings = bindings
        self._on_command = on_command

        # Find device by path or name
        device = None
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
                if device_id in d.name or device_id == path:
                    device = d
                    break
                # Also try vendor:product format
                if ":" in device_id:
                    vendor_str, product_str = device_id.split(":")
                    vendor_id = int(vendor_str, 16)
                    product_id = int(product_str, 16)
                    if d.info.vendor == vendor_id and d.info.product == product_id:
                        device = d
                        break
                d.close()
            except Exception:
                continue

        if not device:
            if self._verbose:
                print(f"[evdev] Device not found: {device_id}")
            return False

        self._device = device

        # Grab device for exclusive access
        try:
            self._device.grab()
            if self._verbose:
                print(f"[evdev] Grabbed device: {device.name}")
        except Exception as e:
            if self._verbose:
                print(f"[evdev] Failed to grab (continuing anyway): {e}")

        self._running = True
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        if self._verbose:
            print(f"[evdev] Listening on {device.name}")

        return True

    def _listen_loop(self) -> None:
        """Main listening loop."""
        import evdev

        try:
            for event in self._device.read_loop():
                if self._stop_event.is_set():
                    break

                # Only handle key press events (value=1)
                if event.type != evdev.ecodes.EV_KEY or event.value != 1:
                    continue

                key_result = evdev.ecodes.KEY.get(event.code)
                if not key_result:
                    continue

                # KEY.get() can return str or tuple[str] for keys with multiple names
                key_name: str = key_result[0] if isinstance(key_result, tuple) else key_result

                # Debounce
                now = time.time() * 1000
                if now - self._last_command_time < self._debounce_ms:
                    continue

                command = self._bindings.get(key_name)
                if command and self._on_command:
                    self._last_command_time = now
                    if self._verbose:
                        print(f"[evdev] {key_name} -> {command}")
                    self._on_command(command, {})

        except Exception as e:
            if self._verbose and self._running:
                print(f"[evdev] Error: {e}")

    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        self._stop_event.set()

        if self._device:
            try:
                self._device.ungrab()
            except Exception:
                pass
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    @property
    def is_running(self) -> bool:
        return self._running
