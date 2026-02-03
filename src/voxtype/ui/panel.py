"""Status panel with HTTP polling for Engine architecture.

Polls /status endpoint and renders a Rich panel with:
- Model loading progress (always visible at top)
- Status info when ready (listening/recording/etc.)
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

from voxtype import __version__

if TYPE_CHECKING:
    from rich.console import Console

class StatusPanel:
    """Status panel that polls /status endpoint.

    Displays a unified panel with:
    - Model loading progress at the top (STT, VAD, TTS)
    - Status info below when loading is complete

    Usage:
        panel = StatusPanel(console, "http://127.0.0.1:8765")
        panel.run()  # Blocks until stopped or error
    """

    # Fixed panel width (content width, excluding borders)
    PANEL_WIDTH = 72

    # Progress bar width (characters)
    PROGRESS_BAR_WIDTH = 25

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

    def _build_progress_bar(self, progress: float, done: bool = False) -> str:
        """Build a progress bar string.

        Args:
            progress: Progress from 0.0 to 1.0
            done: If True, show completed bar in green

        Returns:
            Styled progress bar string
        """
        width = self.PROGRESS_BAR_WIDTH
        if done:
            return "[green]" + "━" * width + "[/]"

        filled = int(progress * width)
        empty = width - filled
        # Bright cyan for loading progress, dim for remaining
        return "[bright_cyan]" + "━" * filled + "[/][dim]" + "━" * empty + "[/]"

    def _build_model_line(
        self,
        label: str,
        model_name: str,
        device: str | None,
        status: str,
        elapsed: float,
        estimated: float,
    ) -> str:
        """Build a single model status line.

        Args:
            label: Model label (STT, VAD, TTS)
            model_name: Model name or "(disabled)"
            device: Device string (e.g., "MLX") or None
            status: Loading status (pending, loading, done)
            elapsed: Elapsed time in seconds
            estimated: Estimated total time in seconds

        Returns:
            Formatted line string
        """
        # Format label and model name
        if model_name == "(disabled)":
            name_part = f"[dim]{label}: (disabled)[/]"
            return name_part

        device_str = f" on [bold green]{device}[/]" if device else ""
        name_part = f"[cyan]{label}:[/] {model_name}{device_str}"

        # Pad name to fixed width for alignment
        # We need to account for markup when calculating visible length
        visible_name = f"{label}: {model_name}" + (f" on {device}" if device else "")
        name_width = 28
        padding = " " * max(0, name_width - len(visible_name))

        if status == "done":
            bar = self._build_progress_bar(1.0, done=True)
            time_str = f"[green]✓ {elapsed:.1f}s[/]"
        elif status == "loading":
            progress = min(elapsed / estimated, 0.99) if estimated > 0 else 0
            bar = self._build_progress_bar(progress)
            eta = max(0, estimated - elapsed)
            time_str = f"[dim]ETA {eta:.0f}s[/]"
        else:  # pending
            bar = self._build_progress_bar(0.0)
            time_str = "[dim]waiting[/]"

        return f"{name_part}{padding}  {bar}  {time_str}"

    def _is_loading(self) -> bool:
        """Check if engine is still loading."""
        loading = self._status.get("loading", {})
        return loading.get("active", False)

    def _build_panel(self) -> Panel:
        """Build the unified status panel."""
        stt = self._status.get("stt", {})
        output = self._status.get("output", {})
        hotkey = self._status.get("hotkey", {})
        engine = self._status.get("engine", {})
        loading = self._status.get("loading", {})
        models = loading.get("models", [])

        # Get model info
        stt_model = stt.get("model_name", "unknown")
        stt_state = stt.get("state", "idle")

        # Device detection (could be enhanced with actual hardware info)
        device = "MLX" if sys.platform == "darwin" else "CPU"

        # Build model status lines
        lines = []

        # Find model loading info
        stt_loading = next((m for m in models if m.get("name") == "stt"), None)
        vad_loading = next((m for m in models if m.get("name") == "vad"), None)

        # STT line
        if stt_loading:
            lines.append(self._build_model_line(
                "STT",
                stt_model,
                device,
                stt_loading.get("status", "done"),
                stt_loading.get("elapsed", 0),
                stt_loading.get("estimated", 20),
            ))
        else:
            # No loading info, assume loaded
            lines.append(self._build_model_line("STT", stt_model, device, "done", 0, 0))

        # VAD line
        if vad_loading:
            lines.append(self._build_model_line(
                "VAD",
                "silero-vad",
                None,
                vad_loading.get("status", "done"),
                vad_loading.get("elapsed", 0),
                vad_loading.get("estimated", 5),
            ))
        else:
            lines.append(self._build_model_line("VAD", "silero-vad", None, "done", 0, 0))

        # TTS line (placeholder - disabled for now)
        lines.append("[dim]TTS: (disabled)[/]")

        # If loading, show minimal panel
        if self._is_loading():
            content = "\n".join(lines)
            version = engine.get("version", __version__)
            return Panel(
                content,
                title=f"voxtype v{version} - Loading",
                border_style="yellow",
                width=self.PANEL_WIDTH,
            )

        # Full panel with status info
        lines.append("")  # Blank line separator
        lines.append(f"Output: {self._format_output(output)}")
        lines.append(f"Hotkey: {self._format_hotkey(hotkey)}")
        lines.append(f"Server: [dim]{self._base_url}[/]")
        lines.append("")  # Blank line separator
        lines.append(f"Status: {self._format_state(stt_state)}")
        lines.append(f"Last: {self._format_last_text()}")

        content = "\n".join(lines)
        version = engine.get("version", __version__)
        return Panel(
            content,
            title=f"voxtype v{version}",
            border_style="green",
            width=self.PANEL_WIDTH,
        )

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

                    # Build unified panel (handles both loading and ready states)
                    live.update(self._build_panel())

                time.sleep(self._poll_interval)

    def stop(self) -> None:
        """Stop the panel."""
        self._running = False
        self._stop_event.set()
