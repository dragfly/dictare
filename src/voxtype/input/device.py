"""Device input source for dedicated hardware (presenter, macro pad, etc.)."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from voxtype.input.base import InputCallback, InputEvent, InputSource


@dataclass
class DeviceProfile:
    """Profile for an input device."""

    name: str
    device_match: str  # Substring to match device name
    bindings: dict[str, str | dict]  # KEY_NAME -> command or {command, args}
    grab_exclusive: bool = True
    debounce_ms: int = 300

    @classmethod
    def from_dict(cls, name: str, data: dict) -> DeviceProfile:
        """Create profile from TOML dict."""
        return cls(
            name=name,
            device_match=data.get("device_match", ""),
            bindings=data.get("bindings", {}),
            grab_exclusive=data.get("grab_exclusive", True),
            debounce_ms=data.get("debounce_ms", 300),
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


class DeviceInputSource(InputSource):
    """Input source for a dedicated device using a profile.

    Unlike keyboard shortcuts, device keys do NOT require modifiers
    because the device is dedicated/exclusive.
    """

    def __init__(self, profile: DeviceProfile, verbose: bool = False) -> None:
        self._profile = profile
        self._verbose = verbose
        self._running = False
        self._device = None
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
            import evdev
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
