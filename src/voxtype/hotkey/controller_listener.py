"""Controller listener for project switching using evdev."""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import evdev


class ControllerListener:
    """Listens to a specific input device for controller commands.

    Uses evdev to listen to a named device (e.g., Bluetooth presenter)
    and maps key presses to commands.
    """

    def __init__(
        self,
        device_name: str,
        key_mappings: dict[str, str],
    ) -> None:
        """Initialize controller listener.

        Args:
            device_name: Name of the input device to listen to.
            key_mappings: Dict mapping evdev key names to command names.
                Example: {"KEY_UP": "project_next", "KEY_DOWN": "project_prev"}

        Raises:
            ImportError: If evdev is not installed.
        """
        import evdev as _evdev  # noqa: F401

        self.device_name = device_name
        self.key_mappings = key_mappings
        self._running = False
        self._thread: threading.Thread | None = None
        self._device: evdev.InputDevice | None = None
        self._stop_event = threading.Event()

    def _find_device_by_name(self) -> evdev.InputDevice | None:
        """Find input device by name."""
        import evdev

        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

        for device in devices:
            if self.device_name in device.name:
                return device
            device.close()

        return None

    def start(self, on_command: Callable[[str], None]) -> bool:
        """Start listening for controller key presses.

        Args:
            on_command: Callback called with command name when a mapped key is pressed.

        Returns:
            True if device was found and listener started, False otherwise.
        """
        import evdev

        self._device = self._find_device_by_name()
        if not self._device:
            return False

        # Build key code to command mapping
        key_code_to_command: dict[int, str] = {}
        for key_name, command in self.key_mappings.items():
            key_code = getattr(evdev.ecodes, key_name, None)
            if key_code is not None:
                key_code_to_command[key_code] = command

        self._running = True
        self._stop_event.clear()

        def listen_loop() -> None:
            try:
                for event in self._device.read_loop():
                    if self._stop_event.is_set():
                        break

                    # Only handle key press events (value == 1)
                    if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                        command = key_code_to_command.get(event.code)
                        if command:
                            on_command(command)
            except OSError:
                # Device closed or disconnected
                pass
            except Exception as e:
                sys.stderr.write(f"Controller listener error: {e}\n")

        self._thread = threading.Thread(target=listen_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop listening for controller events."""
        self._running = False
        self._stop_event.set()

        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

    @staticmethod
    def list_devices() -> list[tuple[str, str]]:
        """List available input devices.

        Returns:
            List of (device_path, device_name) tuples.
        """
        try:
            import evdev

            devices = []
            for path in evdev.list_devices():
                device = evdev.InputDevice(path)
                # Only include devices with keyboard capability
                if evdev.ecodes.EV_KEY in device.capabilities():
                    devices.append((path, device.name))
                device.close()
            return devices
        except Exception:
            return []
