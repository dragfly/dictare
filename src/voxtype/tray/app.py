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

def _patch_pystray_appindicator() -> None:
    """Monkey-patch pystray to use cached icon files on Linux.

    Two problems with pystray's default AppIndicator handling:
    1. Uses tempfile.mktemp() without .png extension — AppIndicator treats
       extensionless paths as icon theme names and falls back to a default.
    2. Creates a NEW temp file on EVERY icon update — AppIndicator must
       reload from the new path, briefly showing a fallback icon (flicker).

    Fix: cache icon files by content hash.  Each unique icon image gets ONE
    stable temp file created once.  Subsequent updates reuse the existing
    path, so AppIndicator loads instantly from an already-present file.
    """
    if sys.platform == "darwin":
        return
    try:
        import io
        import tempfile

        import pystray._util.gtk as _gtk

        _content_cache: dict[int, str] = {}  # PNG content hash → stable path

        def _update_fs_icon_cached(self: _gtk.GtkIcon) -> None:
            """Write icon to a stable cached file (no flicker on swap)."""
            buf = io.BytesIO()
            self.icon.save(buf, "PNG")
            png_bytes = buf.getvalue()
            cache_key = hash(png_bytes)

            if cache_key not in _content_cache:
                path = tempfile.mktemp(suffix=".png")
                with open(path, "wb") as f:
                    f.write(png_bytes)
                _content_cache[cache_key] = path

            self._icon_path = _content_cache[cache_key]
            self._icon_valid = True

        _gtk.GtkIcon._update_fs_icon = _update_fs_icon_cached
    except Exception:
        logger.warning("Could not patch pystray for AppIndicator icons", exc_info=True)

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

def _run_on_main_thread(fn: Callable[[], None]) -> None:
    """Schedule fn on the main thread (required for AppKit on macOS).

    On macOS, pystray runs an NSApplication run loop on the main thread.
    All AppKit mutations (icon, menu, tooltip) MUST happen there.
    PyObjCTools.AppHelper.callAfter dispatches to that run loop.
    """
    if sys.platform != "darwin" or threading.current_thread() is threading.main_thread():
        fn()
        return
    try:
        from PyObjCTools.AppHelper import callAfter

        callAfter(fn)
    except ImportError:
        fn()  # Non-macOS or missing PyObjC — run directly

class TrayApp:
    """System tray application for VoxType.

    This is a UI-only component. It communicates with the engine HTTP API
    to control listening, get status, etc. It does NOT spawn processes.
    """

    def __init__(self) -> None:
        self._icon: pystray.Icon | None = None
        self._state = "disconnected"  # disconnected, restarting, loading, off, listening
        self._progress: int = 0  # 0-100, for loading state
        self._loading_stage: str = ""  # "STT" | "VAD" | ""
        self._restarting = False  # True while engine restart in progress
        self._targets: list[str] = []
        self._current_target: str = ""

        # Icon deduplication — avoids redundant file writes on Linux/AppIndicator
        self._current_icon_name: str = ""

        # Callbacks
        self._on_toggle_listening_cb: Callable[[], None] | None = None
        self._on_target_change: Callable[[str], None] | None = None
        self._on_output_mode_change: Callable[[str], None] | None = None

        # Output mode from config
        self._output_mode: str = "keyboard"  # "keyboard" | "agents"
        self._load_output_mode()

        # Permissions state (from engine /status polling)
        self._microphone_granted = True
        self._input_monitoring_granted = True

        # Status polling
        self._polling = False
        self._poll_thread: threading.Thread | None = None

    def _load_output_mode(self) -> None:
        """Load output mode from config."""
        try:
            from voxtype.config import load_config

            config = load_config()
            self._output_mode = config.output.mode
            logger.info("tray _load_output_mode: config.output.mode=%r", config.output.mode)
        except Exception:
            self._output_mode = "keyboard"
            logger.info("tray _load_output_mode: fallback to keyboard (config load failed)")

    def _create_menu(self) -> pystray.Menu:
        """Create the tray menu."""
        import pystray

        # Status line
        if self._state == "restarting":
            status_text = "Restarting..."
        elif self._state == "loading":
            stage_text = f" {self._loading_stage}..." if self._loading_stage else ""
            status_text = f"Loading{stage_text}"
        elif self._state == "disconnected":
            status_text = "Disconnected"
        else:
            state_display = "IDLE" if self._state == "off" else self._state.upper()
            status_text = state_display

        items = [
            pystray.MenuItem(f"Status: {status_text}", None),
        ]

        # Permission warnings (shown when not granted)
        if sys.platform == "darwin":
            if not self._input_monitoring_granted:
                items.append(
                    pystray.MenuItem(
                        "\u26a0 Grant Input Monitoring",
                        self._on_open_input_monitoring_settings,
                    ),
                )
            if not self._microphone_granted:
                items.append(
                    pystray.MenuItem(
                        "\u26a0 Grant Microphone Permission",
                        self._on_open_microphone_settings,
                    ),
                )

        items.append(pystray.Menu.SEPARATOR)

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

        # Advanced submenu
        advanced_items = [
            pystray.MenuItem("Restart Engine", self._on_restart_engine),
        ]
        items.append(pystray.MenuItem("Advanced", pystray.Menu(*advanced_items)))

        # Settings — opens config file in editor
        items.append(pystray.MenuItem("Settings...", self._on_open_settings))

        items.append(pystray.Menu.SEPARATOR)

        # About submenu (version info)
        from voxtype import __version__

        about_items = [
            pystray.MenuItem(f"VoxType v{__version__}", None),
        ]
        items.append(pystray.MenuItem("About", pystray.Menu(*about_items)))

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
            logger.info("tray menu: user selected output mode %r (was %r)", mode, self._output_mode)
            self._output_mode = mode
            # Persist to config
            try:
                from voxtype.config import set_config_value

                set_config_value("output.mode", mode)
            except Exception:
                logger.warning("tray: failed to persist output.mode=%r to config", mode)
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

    def _on_restart_engine(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Restart the engine via the native service backend (launchd/systemd)."""
        import sys
        import threading

        # Show blue "Restarting..." immediately
        self._restarting = True
        self.set_state("restarting")

        def do_restart() -> None:
            try:
                if sys.platform == "darwin":
                    from voxtype.daemon import launchd as backend
                elif sys.platform == "linux":
                    from voxtype.daemon import systemd as backend
                else:
                    return
                backend.stop()
                backend.start()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("Restart failed: %s", e)
                self._restarting = False
                self.set_state("disconnected")

        threading.Thread(target=do_restart, daemon=True).start()

    def _on_open_accessibility_settings(
        self, icon: pystray.Icon, item: pystray.MenuItem
    ) -> None:
        """Open macOS Accessibility settings."""
        from voxtype.platform.permissions import open_accessibility_settings

        open_accessibility_settings()

    def _on_open_microphone_settings(
        self, icon: pystray.Icon, item: pystray.MenuItem
    ) -> None:
        """Open macOS Microphone settings."""
        from voxtype.platform.permissions import open_microphone_settings

        open_microphone_settings()

    def _on_open_input_monitoring_settings(
        self, icon: pystray.Icon, item: pystray.MenuItem
    ) -> None:
        """Open macOS Input Monitoring settings."""
        from voxtype.platform.permissions import open_input_monitoring_settings

        open_input_monitoring_settings()

    def _on_open_settings(
        self, icon: pystray.Icon, item: pystray.MenuItem
    ) -> None:
        """Open Settings UI in the browser, or config file if engine is down."""
        import webbrowser

        from voxtype.config import load_config

        config = load_config()
        host = config.server.host
        port = config.server.port
        url = f"http://{host}:{port}/settings"

        # Try the web UI first (requires engine running)
        if self._state != "disconnected":
            webbrowser.open(url)
            return

        # Fallback: open config file in editor
        self._open_config_in_editor()

    def _open_config_in_editor(self) -> None:
        """Open config.toml in the system text editor (fallback)."""
        import subprocess

        from voxtype.config import create_default_config, get_config_path

        config_file = get_config_path()
        if not config_file.exists():
            config_file = create_default_config()

        if sys.platform == "darwin":
            subprocess.Popen(["open", "-t", str(config_file)])
        else:
            import os
            import shutil

            editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
            if editor:
                subprocess.Popen([editor, str(config_file)])
            elif shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", str(config_file)])

    def _on_quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Quit the application."""
        if self._icon:
            self._icon.stop()

    def _update_icon(self) -> None:
        """Update the tray icon based on state (dispatches to main thread)."""
        def _do() -> None:
            if not self._icon:
                return

            icon_name = {
                "disconnected": "voxtype_muted",
                "restarting": "voxtype",
                "loading": "voxtype",
                "off": "voxtype",
                "listening": "voxtype_active",
            }.get(self._state, "voxtype_muted")

            perms_ok = self._microphone_granted and self._input_monitoring_granted
            if not perms_ok and self._state not in ("disconnected", "restarting", "loading"):
                icon_name = "voxtype_muted"

            # Skip redundant icon image updates — on Linux/AppIndicator, each
            # update writes a temp PNG file and calls set_icon(), causing
            # visible flicker when multiple SSE events arrive in rapid
            # succession.  Title updates are always applied (lightweight).
            if icon_name != self._current_icon_name:
                self._current_icon_name = icon_name
                self._icon.icon = _load_icon(icon_name)

            title_map = {
                "disconnected": "VoxType — Disconnected",
                "restarting": "VoxType — Restarting…",
                "loading": "VoxType — Loading"
                + (f" {self._loading_stage}…" if self._loading_stage else "…"),
                "off": "VoxType — Idle",
                "listening": "VoxType — Listening",
            }
            self._icon.title = title_map.get(self._state, "VoxType")

        _run_on_main_thread(_do)

    def _update_menu(self) -> None:
        """Update the tray menu (dispatches to main thread)."""
        def _do() -> None:
            if self._icon:
                self._icon.menu = self._create_menu()

        _run_on_main_thread(_do)

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
        if state in ("disconnected", "restarting", "loading", "off", "listening"):
            self._state = state
            self._progress = progress
            self._loading_stage = loading_stage
            # Clear restarting flag once engine reports a real state
            if state not in ("disconnected", "restarting"):
                self._restarting = False
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
        """Set output mode (called by SSE status handler)."""
        if mode != self._output_mode:
            logger.info("tray set_output_mode: %r → %r (from engine SSE)", self._output_mode, mode)
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

    def start_status_streaming(self, host: str = "127.0.0.1", port: int = 8770) -> None:
        """Start listening to engine status changes via SSE.

        Uses subscribe_status() from the OpenVIP SDK with automatic
        reconnection. Push-based: updates arrive instantly on state
        transitions and agent changes. No polling.
        """
        if self._polling:
            return

        def stream() -> None:
            from openvip import Client

            from voxtype.status import resolve_display_state

            client = Client(f"http://{host}:{port}", timeout=2.0)

            # Map shared state names to tray state names
            _tray_state_map = {
                "loading": "loading",
                "listening": "listening",
                "idle": "off",
            }

            status_count = 0

            def _on_disconnect(exc: Exception | None) -> None:
                if exc:
                    logger.info("tray SSE disconnected: %s", exc)
                    # During restart, stay blue instead of going red
                    if not self._restarting:
                        self.set_state("disconnected")

            try:
                for status in client.subscribe_status(
                    reconnect=True,
                    stop=lambda: not self._polling,
                    on_disconnect=_on_disconnect,
                ):
                    if not self._polling:
                        break

                    status_count += 1
                    platform = status.platform or {}
                    state, _ = resolve_display_state(platform)
                    self.set_state(state=_tray_state_map.get(state, "off"))

                    output = platform.get("output", {})
                    agents = output.get("available_agents", [])
                    current_agent = output.get("current_agent", "")
                    engine_mode = output.get("mode", self._output_mode)
                    self.set_targets(agents, current_agent)
                    self.set_output_mode(engine_mode)

                    # Log first status and any mode changes
                    if status_count == 1:
                        logger.info(
                            "tray SSE first status: state=%r, mode=%r, "
                            "current_agent=%r, agents=%r",
                            state, engine_mode, current_agent, agents,
                        )

                    # Update permissions state
                    perms = platform.get("permissions", {})
                    mic_granted = perms.get("microphone", True)
                    im_granted = perms.get("input_monitoring", True)
                    perms_changed = (
                        mic_granted != self._microphone_granted
                        or im_granted != self._input_monitoring_granted
                    )
                    if perms_changed:
                        self._microphone_granted = mic_granted
                        self._input_monitoring_granted = im_granted
                        self._update_menu()
                        self._update_icon()
            except Exception as exc:
                logger.error("tray SSE stream error: %s", exc, exc_info=True)
                if not self._restarting:
                    self.set_state("disconnected")

        self._polling = True
        self._poll_thread = threading.Thread(target=stream, daemon=True)
        self._poll_thread.start()

    def stop_status_polling(self) -> None:
        """Stop status polling."""
        self._polling = False

    def run(self) -> None:
        """Run the tray application (blocking)."""
        import pystray

        # Patch pystray for platform-specific fixes
        _patch_pystray_appindicator()  # Linux: .png extension for temp icons
        _patch_pystray_retina()  # macOS: crisp Retina rendering

        self._icon = pystray.Icon(
            name="voxtype",
            icon=_load_icon("voxtype_muted"),
            title="VoxType",
            menu=self._create_menu(),
        )
        # Sync icon to current state — the SSE thread may have already
        # updated self._state before self._icon was created, causing
        # _update_icon() to skip (guard: if not self._icon: return).
        self._update_icon()
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

    from voxtype import __version__
    from voxtype.config import load_config
    from voxtype.logging.setup import get_default_log_path, setup_logging
    from voxtype.tray.lifecycle import remove_pid, write_pid

    # Write PID for lifecycle management
    write_pid(os.getpid())

    config = load_config()
    host = config.server.host
    port = config.server.port

    # Set up logging — same JSONL file as engine, tagged with source="tray"
    log_path = get_default_log_path("engine")
    setup_logging(
        log_path=log_path,
        level=logging.INFO,
        version=__version__,
        params={"pid": os.getpid()},
        source="tray",
    )
    logger.info(
        "tray starting: config.output.mode=%r, server=%s:%s",
        config.output.mode, host, port,
    )

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

    def on_target_change(target: str) -> None:
        threading.Thread(
            target=lambda: _send_control(f"output.set_agent:{target}"), daemon=True
        ).start()

    app.on_toggle_listening(on_toggle_listening)
    app.on_output_mode_change(on_output_mode_change)
    app.on_target_change(on_target_change)

    # Hide from Dock (tray apps shouldn't show a Dock tile)
    _hide_dock_icon()

    # NOTE: The tray does NOT request Accessibility permission.
    # The engine (running inside Voxtype.app via the Swift launcher) handles all
    # keyboard injection and hotkey listening — those require Accessibility.
    # The tray only reads permission state from the engine's /status endpoint
    # (see start_status_streaming → _on_status → perms["accessibility"]).

    # Hotkey is handled by the engine process — the tray does NOT register
    # its own listener. Having two listeners on the same key causes a double
    # toggle (OFF→LISTENING) that cancels itself out.

    # Subscribe to engine status changes via SSE
    app.start_status_streaming(host=host, port=port)

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
