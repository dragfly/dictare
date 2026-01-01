"""Linux hotkey listener using evdev."""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING, Callable

from voxtype.hotkey.base import HotkeyListener

if TYPE_CHECKING:
    import evdev

class EvdevHotkeyListener(HotkeyListener):
    """Linux hotkey listener using evdev.

    Requires the user to be in the 'input' group or have root access.
    """

    def __init__(
        self,
        key_name: str = "KEY_SCROLLLOCK",
        exclude_device: str | None = None,
    ) -> None:
        """Initialize evdev hotkey listener.

        Args:
            key_name: evdev key name (e.g., KEY_SCROLLLOCK, KEY_F12).
            exclude_device: Device name substring to exclude (e.g., controller device).

        Raises:
            ImportError: If evdev is not installed.
        """
        # Import evdev early to fail fast if not available
        import evdev as _evdev  # noqa: F401

        self.key_name = key_name
        self.exclude_device = exclude_device
        self._running = False
        self._thread: threading.Thread | None = None
        self._device: evdev.InputDevice | None = None
        self._stop_event = threading.Event()

    def _find_keyboard_device(self):
        """Find a keyboard device that has the target key."""
        import evdev

        target_key = getattr(evdev.ecodes, self.key_name, None)
        if target_key is None:
            raise ValueError(f"Unknown key: {self.key_name}")

        # Keywords that indicate non-keyboard devices to avoid
        exclude_keywords = [
            "virtual", "ydotool", "bluetooth", "presenter", "clicker",
            "remote", "consumer control", "system control"
        ]

        # Also exclude the controller device if specified
        if self.exclude_device:
            exclude_keywords.append(self.exclude_device.lower())

        selected_device = None
        devices = []

        try:
            for path in evdev.list_devices():
                device = evdev.InputDevice(path)
                devices.append(device)

                name_lower = device.name.lower()

                # Skip excluded devices
                if any(kw in name_lower for kw in exclude_keywords):
                    continue

                # Check if device has EV_KEY capability
                capabilities = device.capabilities()
                if evdev.ecodes.EV_KEY not in capabilities:
                    continue

                key_caps = capabilities[evdev.ecodes.EV_KEY]

                # First preference: device explicitly has the target key
                if target_key in key_caps:
                    selected_device = device
                    break

            # If no device found with target key, try fallback (first keyboard)
            if selected_device is None:
                for device in devices:
                    name_lower = device.name.lower()
                    if any(kw in name_lower for kw in exclude_keywords):
                        continue
                    if evdev.ecodes.EV_KEY in device.capabilities():
                        selected_device = device
                        break

        finally:
            # Close all devices except the selected one
            for device in devices:
                if device != selected_device:
                    try:
                        device.close()
                    except Exception:
                        pass

        if selected_device is None:
            raise RuntimeError(
                "No keyboard device found.\n"
                "Please add your user to the 'input' group:\n"
                "  sudo usermod -aG input $USER\n"
                "Then log out and back in."
            )

        sys.stderr.write(f"[hotkey] Using device: {selected_device.path} ({selected_device.name})\n")
        sys.stderr.flush()
        return selected_device

    def start(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        """Start listening for hotkey events.

        Args:
            on_press: Callback when hotkey is pressed.
            on_release: Callback when hotkey is released.
        """
        import evdev

        self._device = self._find_keyboard_device()
        target_key = getattr(evdev.ecodes, self.key_name)
        self._running = True
        self._stop_event.clear()

        def listen_loop() -> None:
            try:
                for event in self._device.read_loop():
                    if self._stop_event.is_set():
                        break

                    if event.type == evdev.ecodes.EV_KEY and event.code == target_key:
                        if event.value == 1:  # Key pressed
                            on_press()
                        elif event.value == 0:  # Key released
                            on_release()
                        # value == 2 is key repeat, ignored
            except OSError:
                # Device closed or disconnected
                pass
            except Exception as e:
                sys.stderr.write(f"Hotkey listener error: {e}\n")

        self._thread = threading.Thread(target=listen_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop listening for hotkey events."""
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

    def is_key_available(self) -> bool:
        """Check if the configured key is available on any keyboard."""
        try:
            import evdev

            target_key = getattr(evdev.ecodes, self.key_name, None)
            if target_key is None:
                return False

            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

            for device in devices:
                capabilities = device.capabilities()
                if evdev.ecodes.EV_KEY in capabilities:
                    key_caps = capabilities[evdev.ecodes.EV_KEY]
                    if target_key in key_caps:
                        device.close()
                        return True
                device.close()

            return False
        except Exception:
            return False

    def get_key_name(self) -> str:
        """Get human-readable name of the configured key."""
        # Convert KEY_SCROLLLOCK to ScrollLock, KEY_F12 to F12, etc.
        name = self.key_name
        if name.startswith("KEY_"):
            name = name[4:]
        return name.replace("_", " ").title()

    @staticmethod
    def list_available_keys() -> list[str]:
        """List keys available on connected keyboards.

        Returns:
            List of evdev key names.
        """
        try:
            import evdev

            available_keys: set[str] = set()
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

            for device in devices:
                capabilities = device.capabilities()
                if evdev.ecodes.EV_KEY in capabilities:
                    for key_code in capabilities[evdev.ecodes.EV_KEY]:
                        key_name = evdev.ecodes.KEY.get(key_code)
                        if key_name and isinstance(key_name, str):
                            available_keys.add(key_name)
                device.close()

            return sorted(available_keys)
        except Exception:
            return []

    @staticmethod
    def suggest_fallback_key() -> str | None:
        """Suggest an alternative key if ScrollLock is not available.

        Returns:
            Suggested key name or None if no good alternative.
        """
        preferred_fallbacks = [
            "KEY_SCROLLLOCK",
            "KEY_PAUSE",
            "KEY_F12",
            "KEY_F11",
            "KEY_RIGHTMETA",  # Right Windows/Super key
            "KEY_MENU",
        ]

        available = EvdevHotkeyListener.list_available_keys()

        for key in preferred_fallbacks:
            if key in available:
                return key

        return None
