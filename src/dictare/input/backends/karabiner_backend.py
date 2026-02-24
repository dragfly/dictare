"""Karabiner-Elements backend for device input (macOS only).

Uses Karabiner-Elements for exclusive device grab and command execution.
Karabiner runs shell commands on keypress, which communicate with dictare
via Unix socket.

Requirements:
    brew install --cask karabiner-elements

This backend provides:
    - Exclusive device grab (no double input)
    - Perfect UX for presenter remotes
    - Requires Karabiner-Elements installed
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from dictare.input.backends.base import DeviceBackend

# Karabiner config paths
KARABINER_CONFIG_DIR = Path.home() / ".config" / "karabiner"
KARABINER_COMPLEX_MODS = KARABINER_CONFIG_DIR / "assets" / "complex_modifications"

# Socket for receiving commands from Karabiner
def _get_socket_path() -> str:
    """Get socket path using platform standard location."""
    from dictare.utils.platform import get_socket_dir

    return str(get_socket_dir() / "control.sock")

class KarabinerBackend(DeviceBackend):
    """Karabiner-Elements based device input.

    Pro: Exclusive device grab, perfect UX
    Con: Requires Karabiner-Elements installed (brew install --cask karabiner-elements)
    """

    def __init__(self, verbose: bool = False) -> None:
        self._verbose = verbose
        self._running = False
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._on_command: Callable[[str, dict], None] | None = None

    @property
    def name(self) -> str:
        return "karabiner"

    @property
    def supports_grab(self) -> bool:
        return True

    def is_available(self) -> bool:
        """Check if Karabiner-Elements is installed."""
        if sys.platform != "darwin":
            return False

        # Check if Karabiner CLI exists
        karabiner_cli = Path("/Library/Application Support/org.pqrs/Karabiner-Elements/bin/karabiner_cli")
        return karabiner_cli.exists()

    def list_devices(self) -> list[dict]:
        """List devices from Karabiner.

        Note: Karabiner uses device identifiers differently.
        We use hidapi to list devices, but Karabiner config uses
        vendor_id/product_id format.
        """
        # Delegate to hidapi for device listing
        try:
            from dictare.input.backends.hidapi_backend import HIDAPIBackend
            return HIDAPIBackend().list_devices()
        except Exception:
            return []

    def start(
        self,
        device_id: str,
        bindings: dict[str, str],
        on_command: Callable[[str, dict], None],
    ) -> bool:
        """Start listening for commands via Unix socket.

        The actual key listening is done by Karabiner-Elements.
        This method:
        1. Generates Karabiner config for the device
        2. Starts a socket server to receive commands
        """
        self._on_command = on_command

        # Parse device_id
        try:
            vendor_str, product_str = device_id.split(":")
            vendor_id = int(vendor_str, 16)
            product_id = int(product_str, 16)
        except (ValueError, AttributeError):
            if self._verbose:
                print(f"[karabiner] Invalid device_id: {device_id}")
            return False

        # Generate Karabiner config
        config_path = self._generate_config(vendor_id, product_id, bindings)
        if config_path:
            if self._verbose:
                print(f"[karabiner] Config written to: {config_path}")
                print("[karabiner] Enable 'dictare' rules in Karabiner-Elements preferences")

        # Start socket server
        if not self._start_socket_server():
            return False

        self._running = True
        if self._verbose:
            print(f"[karabiner] Listening on {_get_socket_path()}")

        return True

    def _generate_config(
        self,
        vendor_id: int,
        product_id: int,
        bindings: dict[str, str],
    ) -> Path | None:
        """Generate Karabiner complex modifications config."""
        # Ensure directory exists
        KARABINER_COMPLEX_MODS.mkdir(parents=True, exist_ok=True)

        # Map key names to Karabiner key codes
        key_map = {
            "KEY_PAGEUP": "page_up",
            "KEY_PAGEDOWN": "page_down",
            "KEY_UP": "up_arrow",
            "KEY_DOWN": "down_arrow",
            "KEY_LEFT": "left_arrow",
            "KEY_RIGHT": "right_arrow",
            "KEY_ESC": "escape",
            "KEY_ENTER": "return_or_enter",
            "KEY_SPACE": "spacebar",
            "KEY_B": "b",
            "KEY_P": "p",
            "KEY_S": "s",
            "KEY_F5": "f5",
        }

        rules = []
        for key_name, command in bindings.items():
            karabiner_key = key_map.get(key_name)
            if not karabiner_key:
                continue

            rule = {
                "description": f"dictare: {key_name} -> {command}",
                "manipulators": [
                    {
                        "type": "basic",
                        "from": {
                            "key_code": karabiner_key,
                        },
                        "to": [
                            {
                                "shell_command": f"echo '{command}' | nc -U {_get_socket_path()} 2>/dev/null || true"
                            }
                        ],
                        "conditions": [
                            {
                                "type": "device_if",
                                "identifiers": [
                                    {
                                        "vendor_id": vendor_id,
                                        "product_id": product_id,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
            rules.append(rule)

        config = {
            "title": "dictare presenter controls",
            "rules": rules,
        }

        config_path = KARABINER_COMPLEX_MODS / "dictare.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        return config_path

    def _start_socket_server(self) -> bool:
        """Start Unix socket server for receiving commands."""
        socket_path = _get_socket_path()
        # Remove old socket if exists
        if os.path.exists(socket_path):
            os.unlink(socket_path)

        try:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.bind(socket_path)
            self._socket.listen(1)
            self._socket.settimeout(0.5)  # For clean shutdown
        except Exception as e:
            if self._verbose:
                print(f"[karabiner] Socket error: {e}")
            return False

        self._thread = threading.Thread(target=self._socket_loop, daemon=True)
        self._thread.start()

        return True

    def _socket_loop(self) -> None:
        """Listen for commands on Unix socket."""
        while self._running:
            if self._socket is None:
                break
            try:
                conn, _ = self._socket.accept()
                data = conn.recv(1024).decode().strip()
                conn.close()

                if data and self._on_command:
                    if self._verbose:
                        print(f"[karabiner] Received: {data}")
                    self._on_command(data, {})

            except TimeoutError:
                continue
            except Exception as e:
                if self._running and self._verbose:
                    print(f"[karabiner] Socket error: {e}")
                break

    def stop(self) -> None:
        """Stop listening."""
        self._running = False

        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        socket_path = _get_socket_path()
        if os.path.exists(socket_path):
            try:
                os.unlink(socket_path)
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._running

    @staticmethod
    def get_setup_instructions() -> str:
        """Get setup instructions for users."""
        return """
Karabiner-Elements Setup:

1. Install Karabiner-Elements:
   brew install --cask karabiner-elements

2. Open Karabiner-Elements and grant required permissions

3. Run dictare with your device profile - it will generate Karabiner config

4. In Karabiner-Elements preferences:
   - Go to "Complex Modifications"
   - Click "Add rule"
   - Enable "dictare presenter controls"

5. Your presenter remote now works exclusively with dictare!
"""
