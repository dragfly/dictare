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
        verbose: bool = False,
    ) -> None:
        """Initialize controller listener.

        Args:
            device_name: Name of the input device to listen to.
            key_mappings: Dict mapping evdev key names to command names.
                Example: {"KEY_UP": "project_next", "KEY_DOWN": "project_prev"}
            verbose: Enable debug logging.

        Raises:
            ImportError: If evdev is not installed.
        """
        import evdev as _evdev  # noqa: F401

        self.device_name = device_name
        self.key_mappings = key_mappings
        self.verbose = verbose
        self._running = False
        self._thread: threading.Thread | None = None
        self._device: evdev.InputDevice | None = None
        self._stop_event = threading.Event()

    def _log(self, msg: str) -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            sys.stderr.write(f"[controller] {msg}\n")
            sys.stderr.flush()

    def _find_device_by_name(self) -> evdev.InputDevice | None:
        """Find input device by name that has the mapped keys."""
        import evdev

        # Get the key codes we need
        required_keys = set()
        for key_name in self.key_mappings.keys():
            key_code = getattr(evdev.ecodes, key_name, None)
            if key_code is not None:
                required_keys.add(key_code)

        selected_device = None
        best_match_count = 0
        devices = []

        try:
            for path in evdev.list_devices():
                device = evdev.InputDevice(path)
                devices.append(device)

                if self.device_name not in device.name:
                    continue

                # Check how many of the required keys this device has
                capabilities = device.capabilities()
                if evdev.ecodes.EV_KEY not in capabilities:
                    continue

                key_caps = set(capabilities[evdev.ecodes.EV_KEY])
                match_count = len(required_keys & key_caps)

                self._log(f"Candidate: {device.path} ({device.name}) - {match_count}/{len(required_keys)} keys")

                if match_count > best_match_count:
                    best_match_count = match_count
                    selected_device = device

        finally:
            # Close all devices except the selected one
            for device in devices:
                if device != selected_device:
                    try:
                        device.close()
                    except Exception:
                        pass

        if selected_device:
            self._log(f"Selected: {selected_device.path} ({selected_device.name})")

        return selected_device

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
                self._log(f"Mapping {key_name} ({key_code}) -> {command}")

        # Grab exclusive access so events don't go to terminal
        try:
            self._device.grab()
            self._log("Grabbed exclusive access to device")
        except Exception as e:
            self._log(f"Warning: Could not grab device: {e}")

        self._running = True
        self._stop_event.clear()

        def listen_loop() -> None:
            self._log("Listener thread started")
            try:
                for event in self._device.read_loop():
                    if self._stop_event.is_set():
                        break

                    # Only handle key press events (value == 1)
                    if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                        key_name = evdev.ecodes.KEY.get(event.code, f"UNKNOWN({event.code})")
                        self._log(f"Key pressed: {key_name}")

                        command = key_code_to_command.get(event.code)
                        if command:
                            on_command(command)
            except OSError as e:
                self._log(f"OSError: {e}")
            except Exception as e:
                self._log(f"Error: {e}")
            self._log("Listener thread exiting")

        self._thread = threading.Thread(target=listen_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop listening for controller events."""
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
