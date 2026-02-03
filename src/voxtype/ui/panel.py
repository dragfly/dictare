"""Status panel with HTTP polling for Engine architecture.

Polls /status endpoint and renders a Rich panel with:
- Progress bars during model loading
- Status panel when ready (listening/recording/etc.)
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any

from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from voxtype import __version__

if TYPE_CHECKING:
    from rich.console import Console, RenderableType

class StatusPanel:
    """Status panel that polls /status endpoint.

    Displays:
    - Progress bars during model loading phase
    - Status panel when engine is ready

    Usage:
        panel = StatusPanel(console, "http://127.0.0.1:8765")
        panel.run()  # Blocks until stopped or error
    """

    # Fixed panel width (content width, excluding borders)
    PANEL_WIDTH = 72

    # Max chars for "Last:" text
    LAST_TEXT_MAX_CHARS = 55

    # State display configuration: (label, style)
    STATE_STYLES = {
        "idle": ("IDLE", "dim"),
        "listening": ("LISTENING", "bold green"),
        "recording": ("RECORDING...", "bold cyan"),
        "transcribing": ("TRANSCRIBING...", "bold yellow"),
        "injecting": ("INJECTING...", "bold magenta"),
        "playing": ("PLAYING...", "bold blue"),
        "error": ("ERROR", "bold red"),
    }

    def __init__(
        self,
        console: Console,
        base_url: str = "http://127.0.0.1:8765",
        poll_interval: float = 0.3,
    ) -> None:
        """Initialize the status panel.

        Args:
            console: Rich console for output.
            base_url: Engine HTTP base URL.
            poll_interval: Seconds between polls.
        """
        self._console = console
        self._base_url = base_url.rstrip("/")
        self._poll_interval = poll_interval
        self._running = False
        self._stop_event = threading.Event()

        # Cached status data
        self._status: dict[str, Any] = {}
        self._last_text = ""
        self._last_error: str | None = None

        # Loading state tracking
        self._loading_complete = False
        self._model_tasks: dict[str, Any] = {}  # For progress tracking

        # Connection tracking (to detect engine shutdown)
        self._was_connected = False
        self._consecutive_failures = 0

    def _fetch_status(self) -> dict[str, Any] | None:
        """Fetch /status from engine."""
        try:
            url = f"{self._base_url}/status"
            with urllib.request.urlopen(url, timeout=2) as response:
                return json.loads(response.read().decode())
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, ConnectionResetError, OSError):
            return None

    def _format_state(self, state: str) -> str:
        """Format state with appropriate styling."""
        label, style = self.STATE_STYLES.get(state, (state.upper(), "dim"))
        return f"[{style}]{label}[/{style}]"

    def _format_hotkey(self, hotkey_data: dict) -> str:
        """Format hotkey display string."""
        key = hotkey_data.get("key", "")
        bound = hotkey_data.get("bound", False)

        if key in ("KEY_LEFTMETA", "KEY_RIGHTMETA"):
            key_display = "\u2318 (Command)" if sys.platform == "darwin" else "Super/Meta"
        elif key == "KEY_SCROLLLOCK":
            key_display = "Scroll Lock"
        else:
            key_display = key.replace("KEY_", "")

        if not bound:
            return f"[dim]{key_display} (not bound)[/]"
        return f"[cyan]{key_display}[/] tap: toggle | double-tap: switch"

    def _format_output(self, output_data: dict) -> str:
        """Format output mode display string."""
        mode = output_data.get("mode", "keyboard")
        current = output_data.get("current_agent")
        agents = output_data.get("available_agents", [])

        if mode == "agents":
            if agents:
                parts = []
                for name in agents:
                    if name == current:
                        parts.append(f"[bold green]{name}[/]")
                    else:
                        parts.append(f"[dim]{name}[/]")
                return f"[cyan]agents[/] ({', '.join(parts)})"
            return "[cyan]agents[/] [dim](waiting for agents...)[/]"
        return f"[cyan]{mode}[/]"

    def _format_last_text(self) -> str:
        """Format the last transcribed text."""
        if not self._last_text:
            return "[dim]--[/]"

        if len(self._last_text) > self.LAST_TEXT_MAX_CHARS:
            return f'"{self._last_text[:self.LAST_TEXT_MAX_CHARS]}..."'
        return f'"{self._last_text}"'

    def _build_panel(self) -> Panel:
        """Build the status panel from cached data."""
        stt = self._status.get("stt", {})
        output = self._status.get("output", {})
        hotkey = self._status.get("hotkey", {})
        engine = self._status.get("engine", {})

        # STT info
        model = stt.get("model_name", "unknown")
        language = stt.get("language", "auto")
        state = stt.get("state", "idle")

        # Format device (simplified - could be enhanced)
        device_str = "[bold green]MLX[/]" if sys.platform == "darwin" else "[dim]CPU[/]"

        content = (
            f"Mode: [cyan]transcription[/]\n"
            f"STT: [cyan]{model}[/] on {device_str}\n"
            f"Language: [cyan]{language}[/]\n"
            f"Output: {self._format_output(output)}\n"
            f"Hotkey: {self._format_hotkey(hotkey)}\n"
            f"Server: [dim]{self._base_url}[/]\n"
            f"\n"
            f"Status: {self._format_state(state)}\n"
            f"Last: {self._format_last_text()}"
        )

        version = engine.get("version", __version__)
        return Panel(
            content,
            title=f"voxtype v{version}",
            border_style="green",
            width=self.PANEL_WIDTH,
        )

    def _build_loading_display(self) -> RenderableType:
        """Build loading display with progress bars."""
        loading = self._status.get("loading", {})
        models = loading.get("models", [])

        if not models:
            return Panel(
                "[dim]Initializing...[/]",
                title=f"voxtype v{__version__}",
                border_style="yellow",
                width=self.PANEL_WIDTH,
            )

        # Build a table with progress info
        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold blue", width=20)
        table.add_column(width=40)
        table.add_column(style="dim", width=10)

        for model in models:
            name = model.get("name", "")
            status = model.get("status", "pending")
            elapsed = model.get("elapsed", 0)
            estimated = model.get("estimated", 30)

            if status == "done":
                # Completed
                table.add_row(
                    f"[green]\u2713[/] {name}",
                    "[green]" + "\u2501" * 30 + "[/]",
                    f"[green]{elapsed:.1f}s[/]",
                )
            elif status == "loading":
                # In progress - show bar
                progress = min(elapsed / estimated, 0.99) if estimated > 0 else 0
                filled = int(progress * 30)
                bar = "[cyan]" + "\u2501" * filled + "[/]" + "[dim]" + "\u2501" * (30 - filled) + "[/]"
                eta = max(0, estimated - elapsed)
                table.add_row(
                    f"[cyan]\u25cf[/] {name}",
                    bar,
                    f"[dim]ETA {eta:.0f}s[/]",
                )
            else:
                # Pending
                table.add_row(
                    f"[dim]\u25cb[/] {name}",
                    "[dim]" + "\u2501" * 30 + "[/]",
                    "[dim]waiting[/]",
                )

        return Panel(
            table,
            title=f"voxtype v{__version__} - Loading",
            border_style="yellow",
            width=self.PANEL_WIDTH,
        )

    def _is_loading(self) -> bool:
        """Check if engine is still loading."""
        loading = self._status.get("loading", {})
        return loading.get("active", False)

    def run(self) -> None:
        """Run the panel (blocking).

        Polls /status and updates display until stopped or engine shuts down.
        """
        self._running = True
        self._stop_event.clear()
        self._was_connected = False
        self._consecutive_failures = 0

        with Live(
            Panel("[dim]Connecting...[/]", title="voxtype", border_style="yellow", width=self.PANEL_WIDTH),
            console=self._console,
            refresh_per_second=4,
            transient=False,
        ) as live:
            while self._running and not self._stop_event.is_set():
                # Fetch status
                status = self._fetch_status()

                if status is None:
                    self._consecutive_failures += 1
                    # If we were connected and now failing, engine shut down - exit immediately
                    if self._was_connected:
                        break
                    # Show message while waiting for initial connection
                    live.update(
                        Panel(
                            "[dim]Connecting to engine...[/]\n"
                            f"[dim]URL: {self._base_url}/status[/]",
                            title="voxtype",
                            border_style="yellow",
                            width=self.PANEL_WIDTH,
                        )
                    )
                else:
                    self._was_connected = True
                    self._consecutive_failures = 0
                    self._status = status

                    # Choose display based on loading state
                    if self._is_loading():
                        live.update(self._build_loading_display())
                    else:
                        live.update(self._build_panel())

                time.sleep(self._poll_interval)

    def stop(self) -> None:
        """Stop the panel."""
        self._running = False
        self._stop_event.set()
