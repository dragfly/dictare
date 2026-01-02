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
    SEND_KEYS = {"KEY_B", "KEY_F5", "KEY_S", "KEY_P", "KEY_TAB", "KEY_F4"}

    # Keys that trigger "toggle_listening" command
    TOGGLE_KEYS = {"KEY_ESC"}

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

    def _log(self, msg: str) -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            sys.stderr.write(f"[presenter] {msg}\n")
            sys.stderr.flush()

    def _find_device(self) -> evdev.InputDevice | None:
        """Find the presenter device by name."""
        import evdev

        try:
            for path in evdev.list_devices():
                device = evdev.InputDevice(path)
                if self.device_name in device.name:
                    self._log(f"Found: {device.path} ({device.name})")
                    return device
                device.close()
        except Exception as e:
            self._log(f"Error finding device: {e}")

        return None

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

                    # Map to command
                    if key_name in self.SEND_KEYS:
                        self._log("→ send")
                        on_command("send")
                    elif key_name in self.TOGGLE_KEYS:
                        # Toggle listening state
                        self._listening = not self._listening
                        cmd = "listening_on" if self._listening else "listening_off"
                        self._log(f"→ {cmd}")
                        on_command(cmd)
                    elif key_name in self.AGENT_NEXT_KEYS:
                        self._log("→ agent_next")
                        on_command("agent_next")
                    elif key_name in self.AGENT_PREV_KEYS:
                        self._log("→ agent_prev")
                        on_command("agent_prev")
                    else:
                        self._log(f"→ unmapped")

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
