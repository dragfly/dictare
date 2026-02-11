"""VoxType system tray application."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pystray
    from PIL import Image

# Icon paths relative to this module
ICONS_DIR = Path(__file__).parent / "icons"

def _load_icon(name: str) -> Image.Image:
    """Load an icon from the icons directory."""
    from PIL import Image

    icon_path = ICONS_DIR / f"{name}.png"
    if icon_path.exists():
        return Image.open(icon_path)

    # Fallback: create a simple colored icon
    return _create_fallback_icon(name)

def _create_fallback_icon(name: str) -> Image.Image:
    """Create a simple fallback icon if PNG not found."""
    from PIL import Image, ImageDraw

    # Colors for different states
    colors = {
        "voxtype": "#4A90D9",  # Blue - idle
        "voxtype_active": "#5CB85C",  # Green - listening
        "voxtype_muted": "#D9534F",  # Red - muted
        "voxtype_loading": "#FFA500",  # Orange - loading
    }
    color = colors.get(name, "#4A90D9")

    # Create a 64x64 icon
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw a circle
    margin = 4
    draw.ellipse([margin, margin, size - margin, size - margin], fill=color)

    # Draw a microphone shape (simplified)
    mic_color = "#FFFFFF"
    center_x = size // 2
    mic_width = 12
    mic_height = 24
    mic_top = size // 2 - mic_height // 2 - 4

    # Microphone body
    draw.rounded_rectangle(
        [center_x - mic_width // 2, mic_top, center_x + mic_width // 2, mic_top + mic_height],
        radius=mic_width // 2,
        fill=mic_color,
    )

    # Microphone stand
    stand_top = mic_top + mic_height - 4
    draw.arc(
        [center_x - mic_width, stand_top, center_x + mic_width, stand_top + 12],
        start=0,
        end=180,
        fill=mic_color,
        width=3,
    )
    draw.line(
        [center_x, stand_top + 12, center_x, stand_top + 18],
        fill=mic_color,
        width=3,
    )

    return img

class TrayApp:
    """System tray application for VoxType.

    This is a UI-only component. It communicates with the engine HTTP API
    to control listening, get status, etc. It does NOT spawn processes.
    """

    def __init__(self) -> None:
        self._icon: pystray.Icon | None = None
        self._state = "off"  # off, listening, loading
        self._progress: int = 0  # 0-100, for loading state
        self._loading_stage: str = ""  # "STT" | "VAD" | ""
        self._targets: list[str] = []
        self._current_target: str = ""

        # Callbacks
        self._on_toggle_listening_cb: Callable[[], None] | None = None
        self._on_target_change: Callable[[str], None] | None = None
        self._on_output_mode_change: Callable[[str], None] | None = None

        # Output mode from config
        self._output_mode: str = "keyboard"  # "keyboard" | "agents"
        self._load_output_mode()

        # Status polling
        self._polling = False
        self._poll_thread: threading.Thread | None = None

    def _load_output_mode(self) -> None:
        """Load output mode from config."""
        try:
            from voxtype.config import load_config

            config = load_config()
            self._output_mode = config.output.mode
        except Exception:
            self._output_mode = "keyboard"

    def _create_menu(self) -> pystray.Menu:
        """Create the tray menu."""
        import pystray

        # Status line
        if self._state == "loading":
            stage_text = f" {self._loading_stage}..." if self._loading_stage else ""
            status_text = f"Loading{stage_text}"
        else:
            state_display = self._state.upper()  # OFF or LISTENING
            status_text = state_display

        items = [
            pystray.MenuItem(f"Status: {status_text}", None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]

        # Start/Stop listening toggle
        if self._state == "listening":
            items.append(
                pystray.MenuItem("Stop Listening", self._on_toggle_listening)
            )
        else:
            items.append(
                pystray.MenuItem("Start Listening", self._on_toggle_listening)
            )

        items.append(pystray.Menu.SEPARATOR)

        # Output Mode submenu
        output_display = "Keyboard" if self._output_mode == "keyboard" else "Agents"
        output_items = [
            pystray.MenuItem(
                "Keyboard",
                self._make_output_mode_handler("keyboard"),
                checked=lambda item: self._output_mode == "keyboard",
                radio=True,
            ),
            pystray.MenuItem(
                "Agents",
                self._make_output_mode_handler("agents"),
                checked=lambda item: self._output_mode == "agents",
                radio=True,
            ),
        ]
        items.append(pystray.MenuItem(f"Output: {output_display}", pystray.Menu(*output_items)))

        # Target submenu (only shown when output mode is agents)
        if self._output_mode == "agents" and self._targets:
            target_items = [
                pystray.MenuItem(
                    target,
                    self._make_target_handler(target),
                    checked=lambda item, t=target: self._current_target == t,
                    radio=True,
                )
                for target in self._targets
            ]
            target_display = self._current_target or "None"
            items.append(
                pystray.MenuItem(f"Target: {target_display}", pystray.Menu(*target_items))
            )

        items.append(pystray.Menu.SEPARATOR)

        # About (shows version)
        from voxtype import __version__
        items.append(pystray.MenuItem(f"voxtype v{__version__}", None, enabled=False))

        # Quit
        items.append(pystray.MenuItem("Quit", self._on_quit))

        return pystray.Menu(*items)

    def _make_target_handler(self, target: str) -> Callable:
        """Create a handler for target selection."""

        def handler(icon: pystray.Icon, item: pystray.MenuItem) -> None:
            self._current_target = target
            if self._on_target_change:
                self._on_target_change(target)
            self._update_menu()

        return handler

    def _make_output_mode_handler(self, mode: str) -> Callable:
        """Create a handler for output mode selection."""

        def handler(icon: pystray.Icon, item: pystray.MenuItem) -> None:
            self._output_mode = mode
            # Persist to config
            try:
                from voxtype.config import set_config_value

                set_config_value("output.mode", mode)
            except Exception:
                pass  # Config write failed, but mode is still set in memory
            if self._on_output_mode_change:
                self._on_output_mode_change(mode)
            self._update_menu()

        return handler

    def _on_toggle_listening(
        self, icon: pystray.Icon, item: pystray.MenuItem
    ) -> None:
        """Toggle listening state (OFF <-> LISTENING)."""
        if self._on_toggle_listening_cb:
            self._on_toggle_listening_cb()

    def _on_quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Quit the application."""
        if self._icon:
            self._icon.stop()

    def _update_icon(self) -> None:
        """Update the tray icon based on state."""
        if not self._icon:
            return

        icon_name = {
            "off": "voxtype",
            "listening": "voxtype_active",
            "loading": "voxtype_loading",
        }.get(self._state, "voxtype")

        self._icon.icon = _load_icon(icon_name)

    def _update_menu(self) -> None:
        """Update the tray menu."""
        if self._icon:
            self._icon.menu = self._create_menu()

    def set_state(
        self,
        state: str,
        progress: int = 0,
        loading_stage: str = "",
    ) -> None:
        """Set the tray state externally.

        Args:
            state: Current state ("off", "listening", "loading")
            progress: Loading progress 0-100 (only for loading state)
            loading_stage: What's loading ("STT", "VAD", "")
        """
        if state in ("off", "listening", "loading"):
            self._state = state
            self._progress = progress
            self._loading_stage = loading_stage
            self._update_icon()
            self._update_menu()

    def set_targets(self, targets: list[str], current: str = "") -> None:
        """Set available targets."""
        self._targets = targets
        if current:
            self._current_target = current
        elif targets and not self._current_target:
            self._current_target = targets[0]
        self._update_menu()

    def set_output_mode(self, mode: str) -> None:
        """Set output mode."""
        self._output_mode = mode
        self._update_menu()

    def on_toggle_listening(self, callback: Callable[[], None]) -> None:
        """Register callback for listening toggle."""
        self._on_toggle_listening_cb = callback

    def on_target_change(self, callback: Callable[[str], None]) -> None:
        """Register callback for target change."""
        self._on_target_change = callback

    def on_output_mode_change(self, callback: Callable[[str], None]) -> None:
        """Register callback for output mode change."""
        self._on_output_mode_change = callback

    def get_output_mode(self) -> str:
        """Get current output mode."""
        return self._output_mode

    def start_status_polling(self, host: str = "127.0.0.1", port: int = 8770) -> None:
        """Start polling engine HTTP status every 500ms."""
        if self._polling:
            return

        def poll() -> None:
            import json
            import time
            import urllib.error
            import urllib.request

            status_url = f"http://{host}:{port}/status"

            while self._polling:
                try:
                    with urllib.request.urlopen(status_url, timeout=2) as resp:
                        data = json.loads(resp.read())

                    platform = data.get("platform", {})
                    state = platform.get("state", data.get("state", "idle"))
                    # Map engine states to tray states
                    tray_state = "listening" if state in ("listening", "recording", "transcribing") else "off"
                    self.set_state(state=tray_state)

                    mode = platform.get("mode", "keyboard")
                    self.set_output_mode(mode)

                    output = platform.get("output", {})
                    agents = output.get("available_agents", [])
                    if agents:
                        self.set_targets(agents, output.get("current_agent", ""))
                except (urllib.error.URLError, ConnectionRefusedError, OSError):
                    pass  # Engine not running
                except Exception as e:
                    import sys
                    print(f"Tray poll error: {e}", file=sys.stderr)

                time.sleep(0.5)

            self._polling = False

        self._polling = True
        self._poll_thread = threading.Thread(target=poll, daemon=True)
        self._poll_thread.start()

    def stop_status_polling(self) -> None:
        """Stop status polling."""
        self._polling = False

    def run(self) -> None:
        """Run the tray application (blocking)."""
        import pystray

        self._icon = pystray.Icon(
            name="voxtype",
            icon=_load_icon("voxtype"),
            title="VoxType",
            menu=self._create_menu(),
        )
        self._icon.run()

    def run_detached(self) -> threading.Thread:
        """Run the tray application in a background thread."""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread

def main() -> None:
    """Entry point for standalone tray app (used when run as module).

    Connects to the engine via HTTP API for all operations.
    """
    import json
    import os
    import signal
    import urllib.error
    import urllib.request

    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Error: tray dependencies not installed.", file=sys.stderr)
        print("Install with: pip install voxtype[tray]", file=sys.stderr)
        sys.exit(1)

    from voxtype.config import load_config
    from voxtype.tray.lifecycle import remove_pid, write_pid

    # Write PID for lifecycle management
    write_pid(os.getpid())

    config = load_config()
    host = config.server.host
    port = config.server.port
    control_url = f"http://{host}:{port}/control"

    app = TrayApp()

    def _send_control(command: str) -> None:
        """Send a control command to the engine HTTP API."""
        payload = json.dumps({"command": command}).encode()
        req = urllib.request.Request(
            control_url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5):
                pass
        except (urllib.error.URLError, ConnectionRefusedError, OSError) as e:
            print(f"Engine unavailable: {e}", file=sys.stderr)

    # Connect tray callbacks to engine HTTP API (async to not block UI)
    def on_toggle_listening() -> None:
        threading.Thread(
            target=lambda: _send_control("stt.toggle"), daemon=True
        ).start()

    def on_output_mode_change(mode: str) -> None:
        def do_change() -> None:
            payload = json.dumps({"command": "output.set_mode", "mode": mode}).encode()
            req = urllib.request.Request(
                control_url, data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=5):
                    pass
            except (urllib.error.URLError, ConnectionRefusedError, OSError) as e:
                print(f"Error setting output mode: {e}", file=sys.stderr)

        threading.Thread(target=do_change, daemon=True).start()

    app.on_toggle_listening(on_toggle_listening)
    app.on_output_mode_change(on_output_mode_change)

    # Start global hotkey listener
    def start_hotkey_listener() -> None:
        try:
            from voxtype.hotkey.pynput_listener import PynputHotkeyListener
            from voxtype.hotkey.tap_detector import TapDetector

            hotkey = PynputHotkeyListener(config.hotkey.key)

            tap_detector = TapDetector(
                threshold=0.3,
                on_single_tap=on_toggle_listening,
                on_double_tap=lambda: None,  # TODO: switch agent
            )

            hotkey.start(
                on_press=tap_detector.on_key_down,
                on_release=tap_detector.on_key_up,
                on_other_key=tap_detector.on_other_key,
            )
            print(f"Hotkey registered: {config.hotkey.key}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not register hotkey: {e}", file=sys.stderr)

    threading.Thread(target=start_hotkey_listener, daemon=True).start()

    # Start polling engine HTTP status
    app.start_status_polling(host=host, port=port)

    # Handle SIGINT/SIGTERM gracefully
    def signal_handler(signum: int, frame: object) -> None:
        if app._icon:
            app._icon.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        app.run()
    finally:
        remove_pid()

if __name__ == "__main__":
    main()
