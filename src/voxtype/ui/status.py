"""Live-updating status panel using Rich Live."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rich.live import Live
from rich.panel import Panel

from voxtype import __version__

if TYPE_CHECKING:
    from rich.console import Console

    from voxtype.config import Config

class LiveStatusPanel:
    """Live-updating status panel using Rich Live.

    Displays a box with the current status that updates in-place
    without scrolling the terminal.
    """

    # Fixed panel width (content width, excluding borders)
    # This ensures the panel doesn't resize when content changes
    PANEL_WIDTH = 72

    # Max chars for "Last:" text (leaves room for quotes and "...")
    LAST_TEXT_MAX_CHARS = 55

    # State display configuration: (label, style)
    STATE_STYLES = {
        "OFF": ("OFF", "dim"),
        "LISTENING": ("LISTENING", "bold green"),
        "RECORDING": ("RECORDING...", "bold cyan"),
        "TRANSCRIBING": ("TRANSCRIBING...", "bold yellow"),
        "INJECTING": ("INJECTING...", "bold magenta"),
        "PLAYING": ("PLAYING...", "bold blue"),
    }

    def __init__(
        self,
        config: Config,
        console: Console,
        agent_mode: bool = False,
        log_path: str | None = None,
    ) -> None:
        """Initialize the status panel.

        Args:
            config: Application configuration.
            console: Rich console for output.
            agent_mode: True if running in agent auto-discovery mode.
            log_path: Path to the log file (displayed in panel).
        """
        self._config = config
        self._console = console
        self._agent_mode = agent_mode
        self._agents: list[str] = []  # Updated dynamically
        self._current_agent_index = 0
        self._log_path = log_path
        self._state = "OFF"
        self._last_text = ""
        self._last_text_is_error = False  # True if _last_text is an error message
        self._partial_text = ""  # Realtime partial transcription
        self._live: Live | None = None

        # Pre-compute static content
        self._mode_str = self._compute_mode_str()
        self._stt_str = self._compute_stt_str()
        self._lang = config.stt.language
        self._output_str = self._compute_output_str()
        self._hotkey_str = self._compute_hotkey_str()
        self._log_str = self._compute_log_str()

    def _compute_mode_str(self) -> str:
        """Compute the mode display string."""
        # ProcessingMode removed in v2.61.0 - always transcription mode now
        return "[cyan]transcription[/]"

    def _compute_stt_str(self) -> str:
        """Compute the STT engine display string."""
        from voxtype.utils.hardware import is_mlx_available

        device_str = "[bold yellow on red] CPU [/]"
        gpu_hint = ""

        if not self._config.stt.hw_accel:
            device_str = "[bold yellow on red] CPU [/]"
        elif self._config.stt.device == "cuda":
            from voxtype.cuda_setup import _find_cudnn_path

            if _find_cudnn_path():
                device_str = "[bold green]GPU (CUDA)[/]"
            else:
                device_str = "[bold yellow on red] CPU [/]"
                gpu_hint = " [dim](GPU detected, run: ./install.sh --gpu)[/]"
        elif is_mlx_available():
            device_str = "[bold green]MLX (Apple Silicon)[/]"

        return f"[cyan]{self._config.stt.model}[/] on {device_str}{gpu_hint}"

    def _compute_output_str(self) -> str:
        """Compute the output mode display string."""
        if self._agent_mode:
            if self._agents:
                # Highlight current agent
                parts = []
                for i, name in enumerate(self._agents):
                    if i == self._current_agent_index:
                        parts.append(f"[bold green]{name}[/]")
                    else:
                        parts.append(f"[dim]{name}[/]")
                return f"[cyan]agents[/] ({', '.join(parts)})"
            return "[cyan]agents[/] [dim](waiting for agents...)[/]"
        elif self._config.output.mode == "agents":
            return "[cyan]agents[/]"
        return self._config.output.mode

    def _compute_hotkey_str(self) -> str:
        """Compute the hotkey display string."""
        hotkey = self._config.hotkey.key
        if hotkey in ("KEY_LEFTMETA", "KEY_RIGHTMETA"):
            hotkey_display = "\u2318 (Command)" if sys.platform == "darwin" else "Super/Meta"
        elif hotkey == "KEY_SCROLLLOCK":
            hotkey_display = "Scroll Lock"
        else:
            hotkey_display = hotkey.replace("KEY_", "")

        return f"[cyan]{hotkey_display}[/] tap: toggle | double-tap: switch mode"

    def _compute_log_str(self) -> str:
        """Compute the log file display string."""
        if not self._log_path:
            return "[dim]disabled[/]"
        # Shorten path for display
        from pathlib import Path

        path = Path(self._log_path)
        home = Path.home()
        try:
            rel_path = path.relative_to(home)
            return f"[dim]~/{rel_path}[/]"
        except ValueError:
            return f"[dim]{self._log_path}[/]"

    def _format_state(self) -> str:
        """Format the current state with appropriate styling."""
        label, style = self.STATE_STYLES.get(self._state, (self._state, "dim"))
        return f"[{style}]{label}[/{style}]"

    def _format_last_text(self) -> str:
        """Format the last transcribed text (truncated if needed)."""
        if not self._last_text:
            return "[dim]--[/]"

        # Error messages: bold yellow on red, no quotes
        if self._last_text_is_error:
            text = self._last_text
            if len(text) > self.LAST_TEXT_MAX_CHARS:
                text = text[:self.LAST_TEXT_MAX_CHARS] + "..."
            return f"[bold yellow on red] {text} [/]"

        # Normal text: with quotes
        if len(self._last_text) > self.LAST_TEXT_MAX_CHARS:
            return f'"{self._last_text[:self.LAST_TEXT_MAX_CHARS]}..."'
        return f'"{self._last_text}"'

    def _format_partial_text(self) -> str:
        """Format the partial transcription (realtime mode)."""
        if not self._partial_text:
            return ""
        # Truncate to max chars
        text = self._partial_text
        if len(text) > self.LAST_TEXT_MAX_CHARS:
            text = text[:self.LAST_TEXT_MAX_CHARS] + "..."
        return f'[italic cyan]"{text}"[/]'

    def _build_panel(self) -> Panel:
        """Build the panel with current state."""
        # Build status line with optional partial transcription
        status_line = f"Status: {self._format_state()}"
        partial = self._format_partial_text()
        if partial:
            status_line += f"  {partial}"

        content = (
            f"Mode: {self._mode_str}\n"
            f"STT: {self._stt_str}\n"
            f"Language: [cyan]{self._lang}[/]\n"
            f"Output: {self._output_str}\n"
            f"Hotkey: {self._hotkey_str}\n"
            f"Log: {self._log_str}\n"
            f"\n"
            f"{status_line}\n"
            f"Last: {self._format_last_text()}"
        )
        return Panel(
            content,
            title=f"voxtype v{__version__}",
            border_style="green",
            width=self.PANEL_WIDTH,
        )

    def start(self) -> None:
        """Start live display."""
        self._live = Live(
            self._build_panel(),
            console=self._console,
            refresh_per_second=4,
            transient=False,  # Keep panel visible after stop
        )
        self._live.start()

    def stop(self) -> None:
        """Stop live display."""
        if self._live:
            self._live.stop()
            self._live = None

    def update_state(self, state: str) -> None:
        """Update state and refresh the panel.

        Args:
            state: New state (OFF, LISTENING, RECORDING, TRANSCRIBING, INJECTING, PLAYING)
        """
        self._state = state
        if self._live:
            self._live.update(self._build_panel())

    def update_text(self, text: str, *, is_error: bool = False) -> None:
        """Update last transcribed text and refresh the panel.

        Args:
            text: The transcribed text to display.
            is_error: If True, display as error (bold yellow on red, no quotes).
        """
        self._last_text = text
        self._last_text_is_error = is_error
        self._partial_text = ""  # Clear partial when final arrives
        if self._live:
            self._live.update(self._build_panel())

    def update_partial(self, text: str) -> None:
        """Update partial transcription (realtime mode).

        Args:
            text: The partial transcription to display.
        """
        self._partial_text = text
        if self._live:
            self._live.update(self._build_panel())

    def update_mode(self, mode: str) -> None:
        """Update the processing mode display.

        Args:
            mode: Processing mode (transcription or command)
        """
        if mode == "transcription":
            self._mode_str = "[cyan]transcription[/] (fast)"
        else:
            self._mode_str = "[yellow]command[/] (LLM)"
        if self._live:
            self._live.update(self._build_panel())

    def update_current_agent(self, agent_name: str, index: int) -> None:
        """Update the current agent display.

        Args:
            agent_name: Name of the current agent
            index: Index of the current agent (0-based)
        """
        self._current_agent_index = index
        self._output_str = self._compute_output_str()
        if self._live:
            self._live.update(self._build_panel())

    def update_agents(self, agents: list[str]) -> None:
        """Update the list of available agents.

        Called when agents are discovered or removed.

        Args:
            agents: List of agent IDs.
        """
        self._agents = agents
        # Reset index if current agent no longer exists
        if self._current_agent_index >= len(agents):
            self._current_agent_index = 0
        self._output_str = self._compute_output_str()
        if self._live:
            self._live.update(self._build_panel())
