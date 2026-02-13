"""VoxType system tray application."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pystray
    from PIL import Image

# Icon paths relative to this module
ICONS_DIR = Path(__file__).parent / "icons"


def _load_icon(name: str) -> Image.Image:
    """Load an icon from the icons directory.

    Prefers @2x variant — the Retina patch will set NSImage point-size
    so macOS renders full resolution on HiDPI displays.
    """
    from PIL import Image

    retina_path = ICONS_DIR / f"{name}@2x.png"
    if retina_path.exists():
        return Image.open(retina_path)

    icon_path = ICONS_DIR / f"{name}.png"
    if icon_path.exists():
        return Image.open(icon_path)

    # Fallback: 22x22 transparent
    return Image.new("RGBA", (22, 22), (0, 0, 0, 0))


def _hide_dock_icon() -> None:
    """Hide this process from the macOS Dock.

    Sets NSApplicationActivationPolicyAccessory so only the tray icon shows,
    not a Dock tile with the Python icon.
    """
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication

        NSApplication.sharedApplication().setActivationPolicy_(1)  # Accessory
    except Exception:
        pass


def _ensure_accessibility(prompt: bool = True) -> bool:
    """Check macOS Accessibility permission, optionally prompting the user.

    On macOS, calls AXIsProcessTrustedWithOptions to check (and optionally
    trigger the system dialog for) Accessibility permission.  This is required
    for pynput to monitor global key events.

    Returns True if the process is trusted, False otherwise.
    No-op (returns True) on non-macOS platforms.
    """
    if sys.platform != "darwin":
        return True

    try:
        import ctypes
        import ctypes.util

        as_path = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        cf_path = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"

        appserv = ctypes.cdll.LoadLibrary(as_path)
        cf = ctypes.cdll.LoadLibrary(cf_path)

        # Symbols (Apple API names — noqa N806)
        prompt_key = ctypes.c_void_p.in_dll(  # kAXTrustedCheckOptionPrompt
            appserv, "kAXTrustedCheckOptionPrompt"
        )
        cf_true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")

        # Build options dict: {kAXTrustedCheckOptionPrompt: kCFBooleanTrue}
        cf.CFDictionaryCreateMutable.restype = ctypes.c_void_p
        cf.CFDictionaryCreateMutable.argtypes = [
            ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
        ]
        options = cf.CFDictionaryCreateMutable(None, 1, None, None)

        cf.CFDictionarySetValue.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        cf.CFDictionarySetValue(options, prompt_key, cf_true)

        appserv.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        appserv.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
        trusted = appserv.AXIsProcessTrustedWithOptions(options)

        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease(options)

        if not trusted:
            logger.warning(
                "Accessibility permission not granted — "
                "hotkey monitoring will not work until enabled in "
                "System Settings → Privacy & Security → Accessibility"
            )
        return trusted
    except Exception:
        logger.warning("Could not check Accessibility permission", exc_info=True)
        return False


def _patch_pystray_retina() -> None:
    """Monkey-patch pystray to render icons at full Retina resolution.

    pystray resizes every icon to ``thickness`` pixels (22 on macOS),
    which becomes blurry on Retina (44 physical pixels).  We override
    ``_assert_image`` to:

    1. Convert the PIL image to NSImage at **full pixel resolution**
    2. Set the NSImage *point* size to ``thickness`` so macOS knows
       the image is @2x and renders it pixel-perfect.
    """
    if sys.platform != "darwin":
        return
    try:
        import io

        import AppKit
        import Foundation
        import pystray._darwin as _darwin  # type: ignore[import-untyped]

        def _assert_image_retina(self: _darwin.Icon) -> None:  # type: ignore[override]
            thickness = self._status_bar.thickness()
            pil_img = self._icon

            # Convert PIL → PNG bytes → NSImage
            buf = io.BytesIO()
            pil_img.save(buf, "png")
            ns_data = Foundation.NSData(buf.getvalue())
            ns_image = AppKit.NSImage.alloc().initWithData_(ns_data)

            # Declare point size = menu bar thickness (22pt).
            # If the pixel data is 44px, macOS treats it as @2x automatically.
            ns_image.setSize_((thickness, thickness))

            self._icon_image = ns_image
            self._status_item.button().setImage_(ns_image)

        _darwin.Icon._assert_image = _assert_image_retina
    except Exception:
        logger.warning("Could not patch pystray for Retina icons", exc_info=True)


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
        elif not targets:
            self._current_target = ""
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
            import time
            import urllib.error

            from openvip import Client

            client = Client(f"http://{host}:{port}", timeout=2.0)

            while self._polling:
                try:
                    status = client.get_status()
                    platform = status.platform or {}

                    state = platform.get("state", "idle")
                    # Map engine states to tray states
                    tray_state = "listening" if state in ("listening", "recording", "transcribing") else "off"
                    self.set_state(state=tray_state)

                    mode = platform.get("mode", "keyboard")
                    self.set_output_mode(mode)

                    output = platform.get("output", {})
                    agents = output.get("available_agents", [])
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

        # Patch pystray for crisp Retina rendering
        _patch_pystray_retina()

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
    import os
    import signal
    import urllib.error

    from openvip import Client

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

    client = Client(f"http://{host}:{port}", timeout=5.0)

    app = TrayApp()

    def _send_control(command: str) -> None:
        """Send a control command to the engine HTTP API."""
        try:
            client.control(command)
        except (urllib.error.URLError, ConnectionRefusedError, OSError) as e:
            print(f"Engine unavailable: {e}", file=sys.stderr)

    # Connect tray callbacks to engine HTTP API (async to not block UI)
    def on_toggle_listening() -> None:
        threading.Thread(
            target=lambda: _send_control("stt.toggle"), daemon=True
        ).start()

    def on_output_mode_change(mode: str) -> None:
        threading.Thread(
            target=lambda: _send_control(f"output.set_mode:{mode}"), daemon=True
        ).start()

    app.on_toggle_listening(on_toggle_listening)
    app.on_output_mode_change(on_output_mode_change)

    # Hide from Dock (tray apps shouldn't show a Dock tile)
    _hide_dock_icon()

    # Check Accessibility permission (triggers macOS dialog if needed)
    _ensure_accessibility(prompt=True)

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
