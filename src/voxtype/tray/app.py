"""VoxType system tray application."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from PIL import Image
    import pystray

# Icon paths relative to this module
ICONS_DIR = Path(__file__).parent / "icons"


def _load_icon(name: str) -> "Image.Image":
    """Load an icon from the icons directory."""
    from PIL import Image

    icon_path = ICONS_DIR / f"{name}.png"
    if icon_path.exists():
        return Image.open(icon_path)

    # Fallback: create a simple colored icon
    return _create_fallback_icon(name)


def _create_fallback_icon(name: str) -> "Image.Image":
    """Create a simple fallback icon if PNG not found."""
    from PIL import Image, ImageDraw

    # Colors for different states
    colors = {
        "voxtype": "#4A90D9",  # Blue - idle
        "voxtype_active": "#5CB85C",  # Green - listening
        "voxtype_muted": "#D9534F",  # Red - muted
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
    """System tray application for VoxType."""

    def __init__(self) -> None:
        self._icon: pystray.Icon | None = None
        self._state = "idle"  # idle, listening, muted
        self._targets: list[str] = ["Claude Code", "Cursor", "Terminal"]
        self._current_target: str = "Claude Code"
        self._daemon_running = False
        self._on_start_listening: Callable[[], None] | None = None
        self._on_stop_listening: Callable[[], None] | None = None
        self._on_target_change: Callable[[str], None] | None = None

    def _create_menu(self) -> "pystray.Menu":
        """Create the tray menu."""
        import pystray

        # Status item
        status_text = {
            "idle": "Idle",
            "listening": "Listening...",
            "muted": "Muted",
        }.get(self._state, "Unknown")

        items = [
            pystray.MenuItem(f"Status: {status_text}", None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]

        # Start/Stop listening
        if self._state == "listening":
            items.append(
                pystray.MenuItem("Stop Listening", self._on_toggle_listening)
            )
        else:
            items.append(
                pystray.MenuItem("Start Listening", self._on_toggle_listening)
            )

        # Mute toggle
        mute_text = "Unmute" if self._state == "muted" else "Mute"
        items.append(pystray.MenuItem(mute_text, self._on_toggle_mute))

        items.append(pystray.Menu.SEPARATOR)

        # Target submenu
        target_items = [
            pystray.MenuItem(
                target,
                self._make_target_handler(target),
                checked=lambda item, t=target: self._current_target == t,
                radio=True,
            )
            for target in self._targets
        ]
        items.append(
            pystray.MenuItem("Target", pystray.Menu(*target_items))
        )

        items.append(pystray.Menu.SEPARATOR)

        # Settings (placeholder)
        items.append(pystray.MenuItem("Settings...", self._on_settings, enabled=False))

        items.append(pystray.Menu.SEPARATOR)

        # Quit
        items.append(pystray.MenuItem("Quit", self._on_quit))

        return pystray.Menu(*items)

    def _make_target_handler(self, target: str) -> Callable:
        """Create a handler for target selection."""

        def handler(icon: "pystray.Icon", item: "pystray.MenuItem") -> None:
            self._current_target = target
            if self._on_target_change:
                self._on_target_change(target)
            self._update_menu()

        return handler

    def _on_toggle_listening(
        self, icon: "pystray.Icon", item: "pystray.MenuItem"
    ) -> None:
        """Toggle listening state."""
        if self._state == "listening":
            self._state = "idle"
            if self._on_stop_listening:
                self._on_stop_listening()
        else:
            self._state = "listening"
            if self._on_start_listening:
                self._on_start_listening()
        self._update_icon()
        self._update_menu()

    def _on_toggle_mute(
        self, icon: "pystray.Icon", item: "pystray.MenuItem"
    ) -> None:
        """Toggle mute state."""
        if self._state == "muted":
            self._state = "idle"
        else:
            self._state = "muted"
        self._update_icon()
        self._update_menu()

    def _on_settings(
        self, icon: "pystray.Icon", item: "pystray.MenuItem"
    ) -> None:
        """Open settings (placeholder)."""
        pass

    def _on_quit(self, icon: "pystray.Icon", item: "pystray.MenuItem") -> None:
        """Quit the application."""
        if self._icon:
            self._icon.stop()

    def _update_icon(self) -> None:
        """Update the tray icon based on state."""
        if not self._icon:
            return

        icon_name = {
            "idle": "voxtype",
            "listening": "voxtype_active",
            "muted": "voxtype_muted",
        }.get(self._state, "voxtype")

        self._icon.icon = _load_icon(icon_name)

    def _update_menu(self) -> None:
        """Update the tray menu."""
        if self._icon:
            self._icon.menu = self._create_menu()

    def set_state(self, state: str) -> None:
        """Set the tray state externally."""
        if state in ("idle", "listening", "muted"):
            self._state = state
            self._update_icon()
            self._update_menu()

    def set_targets(self, targets: list[str]) -> None:
        """Set available targets."""
        self._targets = targets
        self._update_menu()

    def set_current_target(self, target: str) -> None:
        """Set current target."""
        self._current_target = target
        self._update_menu()

    def on_start_listening(self, callback: Callable[[], None]) -> None:
        """Register callback for start listening."""
        self._on_start_listening = callback

    def on_stop_listening(self, callback: Callable[[], None]) -> None:
        """Register callback for stop listening."""
        self._on_stop_listening = callback

    def on_target_change(self, callback: Callable[[str], None]) -> None:
        """Register callback for target change."""
        self._on_target_change = callback

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
    """Entry point for standalone tray app (used when run as module)."""
    import os
    import signal

    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Error: tray dependencies not installed.", file=sys.stderr)
        print("Install with: pip install voxtype[tray]", file=sys.stderr)
        sys.exit(1)

    from voxtype.tray.lifecycle import remove_pid, write_pid

    # Write PID for lifecycle management
    write_pid(os.getpid())

    app = TrayApp()

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
