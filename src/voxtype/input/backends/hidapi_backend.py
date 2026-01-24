"""HID API backend for device input.

Uses hidapi package to read from HID devices directly.
Works on macOS and Linux, but does NOT support device grabbing.
This means keypresses go to BOTH voxtype and the focused app.

For exclusive device access on macOS, use the Karabiner backend instead.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from voxtype.input.backends.base import DeviceBackend

from voxtype.input.constants import HID_KEY_MAP

class HIDAPIBackend(DeviceBackend):
    """Direct HID device access using hidapi.

    Pro: Self-contained, no external dependencies
    Con: No device grab - keypresses go to both voxtype AND focused app
    """

    def __init__(self, verbose: bool = False, debounce_ms: int = 300) -> None:
        self._verbose = verbose
        self._debounce_ms = debounce_ms
        self._running = False
        self._device = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_command_time: float = 0
        self._on_command: Callable[[str, dict], None] | None = None
        self._bindings: dict[str, str] = {}
        self._hid_module = None

    @property
    def name(self) -> str:
        return "hidapi"

    @property
    def supports_grab(self) -> bool:
        return False

    def is_available(self) -> bool:
        """Check if hidapi is available."""
        try:
            import hidapi
            return True
        except ImportError:
            pass
        try:
            import hid
            return True
        except ImportError:
            pass
        return False

    def list_devices(self) -> list[dict]:
        """List HID devices."""
        try:
            import hidapi
            return [
                {
                    "vendor_id": d.vendor_id,
                    "product_id": d.product_id,
                    "manufacturer": d.manufacturer_string or "",
                    "product": d.product_string or "",
                    "path": f"{d.vendor_id:04x}:{d.product_id:04x}",
                }
                for d in hidapi.enumerate()
                if d.vendor_id != 0
            ]
        except ImportError:
            pass

        try:
            import hid
            return [
                {
                    "vendor_id": d["vendor_id"],
                    "product_id": d["product_id"],
                    "manufacturer": d.get("manufacturer_string") or "",
                    "product": d.get("product_string") or "",
                    "path": f"{d['vendor_id']:04x}:{d['product_id']:04x}",
                }
                for d in hid.enumerate()
                if d["vendor_id"] != 0
            ]
        except ImportError:
            return []

    def start(
        self,
        device_id: str,
        bindings: dict[str, str],
        on_command: Callable[[str, dict], None],
    ) -> bool:
        """Start listening to the HID device."""
        # Parse device_id as "vendor_id:product_id"
        try:
            vendor_str, product_str = device_id.split(":")
            vendor_id = int(vendor_str, 16)
            product_id = int(product_str, 16)
        except (ValueError, AttributeError):
            if self._verbose:
                print(f"[hidapi] Invalid device_id: {device_id}")
            return False

        # Try hidapi package first, then hid
        try:
            import hidapi
            self._hid_module = hidapi
        except ImportError:
            try:
                import hid
                self._hid_module = hid
            except ImportError:
                if self._verbose:
                    print("[hidapi] No HID package installed")
                return False

        self._bindings = bindings
        self._on_command = on_command

        try:
            if hasattr(self._hid_module, 'Device'):
                # hidapi package API
                self._device = self._hid_module.Device(vid=vendor_id, pid=product_id)
                manufacturer = self._device.manufacturer or "Unknown"
                product = self._device.product or "Unknown"
            else:
                # hid package API
                self._device = self._hid_module.device()
                self._device.open(vendor_id, product_id)
                self._device.set_nonblocking(True)
                manufacturer = self._device.get_manufacturer_string() or "Unknown"
                product = self._device.get_product_string() or "Unknown"
        except Exception as e:
            if self._verbose:
                print(f"[hidapi] Failed to open device: {e}")
            return False

        self._running = True
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        if self._verbose:
            print(f"[hidapi] Connected to {manufacturer} {product}")
            print(f"[hidapi] WARNING: No device grab - keys also go to focused app")

        return True

    def _listen_loop(self) -> None:
        """Main listening loop - poll for HID reports."""
        while self._running and not self._stop_event.is_set():
            try:
                # Read with timeout - API differs between packages
                if hasattr(self._device, 'read'):
                    data = self._device.read(64, timeout_ms=100)
                else:
                    data = self._device.read(64, timeout=100)
                if data:
                    self._handle_report(list(data) if isinstance(data, bytes) else data)
            except Exception as e:
                if self._verbose and self._running:
                    print(f"[hidapi] Read error: {e}")
                break

    def _handle_report(self, data: list[int]) -> None:
        """Handle HID report and extract key presses."""
        for byte in data:
            if byte == 0:
                continue

            key_name = HID_KEY_MAP.get(byte)
            if not key_name:
                continue

            # Debounce
            now = time.time() * 1000
            if now - self._last_command_time < self._debounce_ms:
                continue

            command = self._bindings.get(key_name)
            if command and self._on_command:
                self._last_command_time = now
                if self._verbose:
                    print(f"[hidapi] {key_name} -> {command}")
                self._on_command(command, {})
                return

    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        self._stop_event.set()

        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    @property
    def is_running(self) -> bool:
        return self._running
