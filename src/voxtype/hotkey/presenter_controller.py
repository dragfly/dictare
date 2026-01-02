"""Presenter/clicker controller for voxtype.

Maps presenter remote buttons to voxtype commands.
Handles the quirks of presenter remotes that send keyboard shortcuts
designed for PowerPoint (Shift+F5, Alt+Tab, etc.).
"""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import evdev

# Modifier keys to ignore (they're part of combos, not commands)
MODIFIER_KEYS = {
    "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT",
    "KEY_LEFTCTRL", "KEY_RIGHTCTRL",
    "KEY_LEFTALT", "KEY_RIGHTALT",
    "KEY_LEFTMETA", "KEY_RIGHTMETA",
}


class PresenterController:
    """Controller for presenter remotes / clickers.

    Presenter remotes typically send keyboard shortcuts for PowerPoint.
    This class abstracts those into simple commands:
    - send: Submit the current input (Enter)
    - toggle_listening: Toggle listening mode on/off

    Default mappings (for typical presenter):
    - PLAY button (KEY_B, KEY_F5, KEY_S, KEY_P) → send
    - ESC button (KEY_ESC) → toggle_listening
    - UP/DOWN → agent_next/agent_prev
    """

    # Keys that trigger "send" command (PLAY button variants)
    # Note: KEY_ESC added because some presenters alternate between F5 and ESC on same button
    SEND_KEYS = {"KEY_F5", "KEY_S", "KEY_P", "KEY_TAB", "KEY_F4", "KEY_ESC"}

    # Keys that trigger "toggle_listening" command
    TOGGLE_KEYS = {"KEY_B"}

    # Keys for agent switching
    AGENT_NEXT_KEYS = {"KEY_UP", "KEY_PAGEUP"}
    AGENT_PREV_KEYS = {"KEY_DOWN", "KEY_PAGEDOWN"}

    def __init__(
        self,
        device_name: str,
        verbose: bool = False,
    ) -> None:
        """Initialize presenter controller.

        Args:
            device_name: Name of the input device to listen to.
            verbose: Enable debug logging.
        """
        try:
            import evdev as _evdev  # noqa: F401
        except ImportError:
            raise ImportError("evdev is required for controller support")

        self.device_name = device_name
        self.verbose = verbose
        self._running = False
        self._thread: threading.Thread | None = None
        self._device: evdev.InputDevice | None = None
        self._stop_event = threading.Event()
        self._listening = True  # Track listening state for toggle
        self._last_command_time: float = 0  # For debouncing
        self._debounce_ms: int = 300  # Ignore commands within this window

    def _log(self, msg: str) -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            sys.stderr.write(f"[presenter] {msg}\n")
            sys.stderr.flush()

    def _find_device(self) -> evdev.InputDevice | None:
        """Find the presenter device by name.

        Prefers devices with 'keyboard' or 'kbd' in their by-id symlink,
        since presenters often register as multiple devices (keyboard, mouse, system control).
        """
        import evdev
        import os

        # Build a map of device path -> by-id symlink name
        by_id_map: dict[str, str] = {}
        by_id_dir = "/dev/input/by-id"
        if os.path.isdir(by_id_dir):
            for name in os.listdir(by_id_dir):
                try:
                    target = os.path.realpath(os.path.join(by_id_dir, name))
                    by_id_map[target] = name
                except OSError:
                    pass

        candidates = []
        try:
            for path in evdev.list_devices():
                device = evdev.InputDevice(path)
                if self.device_name in device.name:
                    # Check if this is the keyboard device via by-id symlink
                    real_path = os.path.realpath(device.path)
                    by_id_name = by_id_map.get(real_path, "")
                    is_kbd = "kbd" in by_id_name.lower() or "keyboard" in by_id_name.lower()
                    candidates.append((device, is_kbd, by_id_name))
                    self._log(f"Candidate: {device.path} ({by_id_name}) kbd={is_kbd}")
                else:
                    device.close()
        except Exception as e:
            self._log(f"Error finding device: {e}")
            return None

        if not candidates:
            return None

        # Prefer keyboard device
        candidates.sort(key=lambda x: (not x[1], x[0].path))  # kbd first, then by path

        # Close non-selected devices
        selected = candidates[0][0]
        for device, _, _ in candidates[1:]:
            device.close()

        self._log(f"Selected: {selected.path} ({selected.name})")
        return selected

    def start(self, on_command: Callable[[str], None]) -> bool:
        """Start listening for presenter button presses.

        Args:
            on_command: Callback with command name:
                - "send": Submit input
                - "listening_on": Start listening
                - "listening_off": Stop listening
                - "agent_next": Next agent
                - "agent_prev": Previous agent

        Returns:
            True if device was found and listener started.
        """
        import evdev

        self._device = self._find_device()
        if not self._device:
            return False

        # Grab exclusive access
        try:
            self._device.grab()
            self._log("Grabbed exclusive access")
        except Exception as e:
            self._log(f"Could not grab device: {e}")

        self._running = True
        self._stop_event.clear()

        def listen_loop() -> None:
            self._log("Listener started")
            try:
                for event in self._device.read_loop():
                    if self._stop_event.is_set():
                        break

                    # Only handle key press events (value == 1)
                    if event.type != evdev.ecodes.EV_KEY or event.value != 1:
                        continue

                    key_name = evdev.ecodes.KEY.get(event.code, f"UNKNOWN({event.code})")

                    # Skip modifier keys
                    if key_name in MODIFIER_KEYS:
                        self._log(f"Ignoring modifier: {key_name}")
                        continue

                    self._log(f"Key: {key_name}")

                    # Map to command (with debounce)
                    import time
                    now = time.time() * 1000  # ms
                    if now - self._last_command_time < self._debounce_ms:
                        self._log("→ debounced")
                        continue

                    cmd = None
                    if key_name in self.SEND_KEYS:
                        cmd = "send"
                    elif key_name in self.TOGGLE_KEYS:
                        # Toggle listening state
                        self._listening = not self._listening
                        cmd = "listening_on" if self._listening else "listening_off"
                    elif key_name in self.AGENT_NEXT_KEYS:
                        cmd = "agent_next"
                    elif key_name in self.AGENT_PREV_KEYS:
                        cmd = "agent_prev"

                    if cmd:
                        self._log(f"→ {cmd}")
                        self._last_command_time = now
                        on_command(cmd)
                    else:
                        self._log("→ unmapped")

            except OSError as e:
                self._log(f"OSError: {e}")
            except Exception as e:
                self._log(f"Error: {e}")
            self._log("Listener stopped")

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
