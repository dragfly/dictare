"""Device input source for dedicated hardware (presenter, macro pad, etc.)."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voxtype.input.base import InputCallback, InputEvent, InputSource
from voxtype.input.constants import HID_KEY_MAP

@dataclass
class DeviceProfile:
    """Profile for an input device."""

    name: str
    device_match: str  # Substring to match device name (evdev/Linux)
    bindings: dict[str, str | dict]  # KEY_NAME -> command or {command, args}
    grab_exclusive: bool = True
    debounce_ms: int = 300
    # USB HID matching (hidapi/macOS)
    vendor_id: int | None = None
    product_id: int | None = None

    @classmethod
    def from_dict(cls, name: str, data: dict) -> DeviceProfile:
        """Create profile from TOML dict."""
        # Parse vendor_id/product_id (can be int or hex string like "0x1234")
        vendor_id = data.get("vendor_id")
        if isinstance(vendor_id, str):
            vendor_id = int(vendor_id, 16) if vendor_id.startswith("0x") else int(vendor_id)

        product_id = data.get("product_id")
        if isinstance(product_id, str):
            product_id = int(product_id, 16) if product_id.startswith("0x") else int(product_id)

        return cls(
            name=name,
            device_match=data.get("device_match", ""),
            bindings=data.get("bindings", {}),
            grab_exclusive=data.get("grab_exclusive", True),
            debounce_ms=data.get("debounce_ms", 300),
            vendor_id=vendor_id,
            product_id=product_id,
        )

    @classmethod
    def load_from_file(cls, path: Path) -> DeviceProfile | None:
        """Load profile from TOML file."""
        try:
            import tomllib

            with open(path, "rb") as f:
                data = tomllib.load(f)
            return cls.from_dict(path.stem, data)
        except Exception:
            return None

    @property
    def has_hid_ids(self) -> bool:
        """Check if HID vendor/product IDs are configured."""
        return self.vendor_id is not None and self.product_id is not None

class DeviceInputSource(InputSource):
    """Input source for a dedicated device using a profile.

    Unlike keyboard shortcuts, device keys do NOT require modifiers
    because the device is dedicated/exclusive.
    """

    def __init__(self, profile: DeviceProfile, verbose: bool = False) -> None:
        self._profile = profile
        self._verbose = verbose
        self._running = False
        self._device: Any = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_command_time: float = 0
        self._on_input: InputCallback | None = None

    def start(self, on_input: InputCallback) -> bool:
        """Start listening to the device."""
        if sys.platform != "linux":
            # evdev only works on Linux
            if self._verbose:
                print(f"[device] {self._profile.name}: evdev not available on {sys.platform}")
            return False

        try:
            import evdev  # noqa: F401
        except ImportError:
            if self._verbose:
                print(f"[device] {self._profile.name}: evdev not installed")
            return False

        self._on_input = on_input
        self._device = self._find_device()

        if not self._device:
            if self._verbose:
                print(f"[device] {self._profile.name}: device not found")
            return False

        if self._profile.grab_exclusive:
            try:
                self._device.grab()
            except Exception as e:
                if self._verbose:
                    print(f"[device] {self._profile.name}: failed to grab: {e}")

        self._running = True
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        if self._verbose:
            print(f"[device] {self._profile.name}: started on {self._device.name}")

        return True

    def _find_device(self):
        """Find device matching profile."""
        import evdev

        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
                if self._profile.device_match in device.name:
                    return device
                device.close()
            except Exception:
                continue
        return None

    def _listen_loop(self) -> None:
        """Main listening loop."""
        import evdev

        try:
            for event in self._device.read_loop():
                if self._stop_event.is_set():
                    break

                if event.type != evdev.ecodes.EV_KEY or event.value != 1:
                    continue

                key_name = evdev.ecodes.KEY.get(event.code)
                if not key_name:
                    continue

                # Debounce
                now = time.time() * 1000
                if now - self._last_command_time < self._profile.debounce_ms:
                    continue

                binding = self._profile.bindings.get(key_name)
                if binding:
                    self._last_command_time = now
                    self._emit_command(key_name, binding)
        except Exception as e:
            if self._verbose and self._running:
                print(f"[device] {self._profile.name}: error: {e}")

    def _emit_command(self, key_name: str, binding: str | dict) -> None:
        """Emit command event from binding."""
        if isinstance(binding, str):
            command = binding
            args = {}
        else:
            command = binding.get("command", "")
            args = binding.get("args", {})

        if self._verbose:
            print(f"[device] {self._profile.name}: {key_name} -> {command}")

        event = InputEvent(
            command=command,
            args=args,
            source=f"device:{self._profile.name}",
        )

        if self._on_input:
            self._on_input(event)

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
    def source_name(self) -> str:
        return f"Device: {self._profile.name}"

    @property
    def is_running(self) -> bool:
        return self._running

class HIDDeviceInputSource(InputSource):
    """Input source for HID devices using hidapi (cross-platform).

    Works on macOS and Linux. Requires vendor_id and product_id in profile.
    """

    def __init__(self, profile: DeviceProfile, verbose: bool = False) -> None:
        self._profile = profile
        self._verbose = verbose
        self._running = False
        self._device: Any = None
        self._hid_module: Any = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_command_time: float = 0
        self._on_input: InputCallback | None = None

    def start(self, on_input: InputCallback) -> bool:
        """Start listening to the HID device."""
        if not self._profile.has_hid_ids:
            if self._verbose:
                print(f"[hid] {self._profile.name}: no vendor_id/product_id configured")
            return False

        # Try hid package first, then hidapi
        hid_module: Any = None
        try:
            import hid
            hid_module = hid
        except ImportError:
            try:
                import hidapi
                hid_module = hidapi
            except ImportError:
                if self._verbose:
                    print(f"[hid] {self._profile.name}: no HID package installed")
                return False

        self._on_input = on_input
        self._hid_module = hid_module

        try:
            if hasattr(hid_module, 'device'):
                # hid package API
                self._device = hid_module.device()
                self._device.open(self._profile.vendor_id, self._profile.product_id)
                self._device.set_nonblocking(True)
                manufacturer = self._device.get_manufacturer_string() or "Unknown"
                product = self._device.get_product_string() or "Unknown"
            else:
                # hidapi package API
                self._device = hid_module.Device(
                    vid=self._profile.vendor_id,
                    pid=self._profile.product_id
                )
                manufacturer = self._device.manufacturer or "Unknown"
                product = self._device.product or "Unknown"
        except Exception as e:
            if self._verbose:
                print(f"[hid] {self._profile.name}: failed to open: {e}")
            return False

        self._running = True
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        if self._verbose:
            print(f"[hid] {self._profile.name}: connected to {manufacturer} {product}")

        return True

    def _listen_loop(self) -> None:
        """Main listening loop - poll for HID reports."""
        while self._running and not self._stop_event.is_set():
            try:
                # Read with timeout - API differs between packages
                if hasattr(self._device, 'read'):
                    # hid package: read(size, timeout_ms)
                    data = self._device.read(64, timeout_ms=100)
                else:
                    # hidapi package: read(size, timeout=ms)
                    data = self._device.read(64, timeout=100)
                if data:
                    self._handle_report(list(data) if isinstance(data, bytes) else data)
            except Exception as e:
                if self._verbose and self._running:
                    print(f"[hid] {self._profile.name}: read error: {e}")
                break

    def _handle_report(self, data: list[int]) -> None:
        """Handle HID report and extract key presses."""
        # HID keyboard reports typically have format:
        # [modifier, reserved, key1, key2, key3, key4, key5, key6]
        # Or for consumer devices, different formats

        # Try to find a key code in the report
        for byte in data:
            if byte == 0:
                continue

            key_name = HID_KEY_MAP.get(byte)
            if not key_name:
                continue

            # Debounce
            now = time.time() * 1000
            if now - self._last_command_time < self._profile.debounce_ms:
                continue

            binding = self._profile.bindings.get(key_name)
            if binding:
                self._last_command_time = now
                self._emit_command(key_name, binding)
                return  # Only one command per report

    def _emit_command(self, key_name: str, binding: str | dict) -> None:
        """Emit command event from binding."""
        if isinstance(binding, str):
            command = binding
            args = {}
        else:
            command = binding.get("command", "")
            args = binding.get("args", {})

        if self._verbose:
            print(f"[hid] {self._profile.name}: {key_name} -> {command}")

        event = InputEvent(
            command=command,
            args=args,
            source=f"hid:{self._profile.name}",
        )

        if self._on_input:
            self._on_input(event)

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
    def source_name(self) -> str:
        return f"HID: {self._profile.name}"

    @property
    def is_running(self) -> bool:
        return self._running
