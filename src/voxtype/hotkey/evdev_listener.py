"""Linux hotkey listener using evdev."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from voxtype.hotkey.base import HotkeyListener

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import evdev

class EvdevHotkeyListener(HotkeyListener):
    """Linux hotkey listener using evdev.

    Requires the user to be in the 'input' group or have root access.
    """

    def __init__(
        self,
        key_name: str = "KEY_SCROLLLOCK",
        target_device: str | None = None,
    ) -> None:
        """Initialize evdev hotkey listener.

        Args:
            key_name: evdev key name (e.g., KEY_SCROLLLOCK, KEY_F12).
            target_device: Device name substring to prefer (e.g., specific keyboard).

        Raises:
            ImportError: If evdev is not installed.
        """
        # Import evdev early to fail fast if not available
        import evdev as _evdev  # noqa: F401

        self.key_name = key_name
        self.target_device = target_device
        self._running = False
        self._thread: threading.Thread | None = None
        self._device: evdev.InputDevice | None = None
        self._stop_event = threading.Event()
        self._selected_device_info: tuple[str, str] | None = None  # (path, name)
        self._on_other_key: Callable[[], None] | None = None
        self._capture_event: threading.Event | None = None
        self._captured_key: str | None = None

    def _find_keyboard_device(self):
        """Find a keyboard device that has the target key.

        Prioritizes:
        1. User-specified target_device (if set)
        2. Devices with 'keyboard' in the name
        3. Any device with the target key
        """
        import evdev

        target_key = getattr(evdev.ecodes, self.key_name, None)
        if target_key is None:
            raise ValueError(f"Unknown key: {self.key_name}")

        # Keywords that indicate non-keyboard devices to avoid
        exclude_keywords = [
            "virtual", "ydotool", "bluetooth", "presenter", "clicker",
            "remote", "consumer control", "system control"
        ]

        user_specified = None     # Priority 0: user-specified device
        keyboard_with_key = None  # Priority 1: has "keyboard" in name + has target key
        any_with_key = None       # Priority 2: has target key (no "keyboard" in name)
        devices = []

        try:
            for path in evdev.list_devices():
                device = evdev.InputDevice(path)
                devices.append(device)

                name_lower = device.name.lower()

                # Skip excluded devices (unless user specifically requested it)
                if any(kw in name_lower for kw in exclude_keywords):
                    # But if user specified this device, allow it
                    if not (self.target_device and self.target_device.lower() in name_lower):
                        continue

                # Check if device has EV_KEY capability
                capabilities = device.capabilities()
                if evdev.ecodes.EV_KEY not in capabilities:
                    continue

                key_caps = capabilities[evdev.ecodes.EV_KEY]

                # Check if device has the target key
                if target_key in key_caps:
                    # Priority 0: user-specified device
                    if self.target_device and self.target_device.lower() in name_lower:
                        user_specified = device
                        break  # User knows what they want
                    elif "keyboard" in name_lower:
                        # Priority 1: real keyboard with the key
                        keyboard_with_key = device
                        if not self.target_device:
                            break  # Found the best auto option
                    elif any_with_key is None:
                        # Priority 2: first device with the key (keep looking for keyboard)
                        any_with_key = device

            # Select best available device
            selected_device = user_specified or keyboard_with_key or any_with_key

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

        # Store device info for later retrieval
        self._selected_device_info = (selected_device.path, selected_device.name)
        return selected_device

    def start(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        on_other_key: Callable[[], None] | None = None,
    ) -> None:
        """Start listening for hotkey events.

        Args:
            on_press: Callback when hotkey is pressed.
            on_release: Callback when hotkey is released.
            on_other_key: Callback when any OTHER key is pressed (for combo detection).
        """
        import evdev

        self._device = self._find_keyboard_device()
        if self._device is None:
            raise RuntimeError("No keyboard device found")
        target_key = getattr(evdev.ecodes, self.key_name)
        self._running = True
        self._stop_event.clear()
        self._on_other_key = on_other_key

        logger.info(
            "Evdev hotkey started: key=%s, device=%s (%s)",
            self.key_name, self._device.path, self._device.name,
        )

        def listen_loop() -> None:
            assert self._device is not None
            try:
                logger.debug("Evdev read_loop starting on %s", self._device.path)
                for event in self._device.read_loop():
                    if self._stop_event.is_set():
                        break

                    if event.type == evdev.ecodes.EV_KEY:
                        # Capture mode: record any key press and signal waiter.
                        cap = self._capture_event
                        if cap is not None and event.value == 1:
                            key_name = evdev.ecodes.KEY.get(event.code)
                            if isinstance(key_name, str):
                                self._captured_key = key_name
                                cap.set()
                            continue

                        if event.code == target_key:
                            if event.value == 1:  # Key pressed
                                on_press()
                            elif event.value == 0:  # Key released
                                on_release()
                            # value == 2 is key repeat, ignored
                        elif event.value == 1 and self._on_other_key:
                            # Any other key pressed - notify for combo detection
                            self._on_other_key()
                logger.info("Evdev read_loop exited normally")
            except OSError as e:
                logger.warning("Evdev device error: %s (%s)", e, self._device.path)
            except Exception as e:
                logger.error("Evdev listener error: %s", e, exc_info=True)

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

    def capture_next_key(self, timeout: float = 10.0) -> str | None:
        """Capture the next physical key press and return its evdev name."""
        if self._thread is None or not self._thread.is_alive():
            return None
        event = threading.Event()
        self._captured_key = None
        self._capture_event = event
        try:
            event.wait(timeout=timeout)
        finally:
            self._capture_event = None
        return self._captured_key

    def is_key_available(self) -> bool:
        """Check if the configured key is available on a usable keyboard.

        Uses the same filtering and prioritization as _find_keyboard_device()
        to avoid false positives when key exists only on virtual/excluded devices.
        Prioritizes devices with 'keyboard' in the name.
        """
        try:
            import evdev

            target_key = getattr(evdev.ecodes, self.key_name, None)
            if target_key is None:
                return False

            # Same exclude keywords as _find_keyboard_device
            exclude_keywords = [
                "virtual", "ydotool", "bluetooth", "presenter", "clicker",
                "remote", "consumer control", "system control"
            ]

            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
            found_on_keyboard = False
            found_on_any = False

            for device in devices:
                name_lower = device.name.lower()

                # Skip excluded devices (same as _find_keyboard_device)
                if any(kw in name_lower for kw in exclude_keywords):
                    device.close()
                    continue

                capabilities = device.capabilities()
                if evdev.ecodes.EV_KEY in capabilities:
                    key_caps = capabilities[evdev.ecodes.EV_KEY]
                    if target_key in key_caps:
                        if "keyboard" in name_lower:
                            found_on_keyboard = True
                            device.close()
                            break  # Found on real keyboard, done
                        else:
                            found_on_any = True
                device.close()

            return found_on_keyboard or found_on_any
        except Exception:
            return False

    def get_key_name(self) -> str:
        """Get human-readable name of the configured key."""
        # Convert KEY_SCROLLLOCK to ScrollLock, KEY_F12 to F12, etc.
        name = self.key_name
        if name.startswith("KEY_"):
            name = name[4:]
        return name.replace("_", " ").title()

    def get_selected_device_info(self) -> tuple[str, str] | None:
        """Get the path and name of the selected device.

        Returns:
            Tuple of (path, name) or None if not yet selected.
        """
        return self._selected_device_info

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
