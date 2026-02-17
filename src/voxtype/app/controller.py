"""AppController - application-level logic and user interaction.

The AppController is the central coordinator for foreground mode (CLI and Tray).
It creates and manages:
- Engine (STT, VAD, audio, pipeline, agents)
- HTTP server (OpenVIP protocol + app endpoints)
- KeyboardBindingManager (hotkeys, shortcuts, device profiles)

CLI and Tray both:
1. Create AppController(config)
2. Call controller.start()
3. Run UI in another thread (polling HTTP for status)
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from voxtype.app.bindings import KeyboardBindingManager
    from voxtype.config import Config
    from voxtype.core.engine import VoxtypeEngine

logger = logging.getLogger(__name__)

class AppController:
    """Application controller for foreground mode.

    Manages the lifecycle of engine and input bindings.
    Exposes app-level commands (toggle_listening, next_agent, etc.)
    that are stateful and non-atomic.

    Usage:
        controller = AppController(config)
        controller.start()
        # ... run UI in another thread ...
        controller.stop()
    """

    def __init__(self, config: Config) -> None:
        """Initialize controller.

        Args:
            config: Application configuration.
        """
        self._config = config
        self._engine: VoxtypeEngine | None = None
        self._http_server: Any = None  # OpenVIPServer
        self._bindings: KeyboardBindingManager | None = None
        self._logger: Any = None  # JSONLLogger
        self._running = False
        self._shutdown_event = threading.Event()

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def start(
        self,
        *,
        start_listening: bool = True,
        mode: str = "foreground",
        with_bindings: bool = True,
    ) -> None:
        """Start the application.

        Creates and starts:
        1. Engine (loads models, starts HTTP server in agent mode)
        2. KeyboardBindingManager (hotkeys, shortcuts) - if with_bindings=True

        Args:
            start_listening: If True, start listening immediately.
            mode: "foreground" or "daemon".
            with_bindings: If True, start keyboard bindings (foreground only).
        """
        from voxtype.app.bindings import KeyboardBindingManager
        from voxtype.core.engine import create_engine
        from voxtype.core.events import EngineEvents

        engine_ref: list[VoxtypeEngine | None] = [None]
        config = self._config  # Capture for closure

        class ControllerEvents(EngineEvents):
            """Event handler for audio feedback and logging."""

            def on_state_change(self, old: Any, new: Any, trigger: str) -> None:
                from voxtype.audio.beep import (
                    get_sound_for_event,
                    play_audio,
                    play_sound_file_async,
                )
                from voxtype.core.fsm import AppState

                eng = engine_ref[0]
                ctrl = eng._controller if eng else None
                pause = not config.audio.headphones_mode

                if new == AppState.LISTENING and old == AppState.OFF:
                    enabled, path = get_sound_for_event(config.audio, "start")
                    if enabled:
                        play_audio(path, pause_mic=pause, controller=ctrl)
                elif new == AppState.OFF:
                    enabled, path = get_sound_for_event(config.audio, "stop")
                    if enabled:
                        play_audio(path, pause_mic=False)
                elif new == AppState.TRANSCRIBING:
                    enabled, path = get_sound_for_event(config.audio, "transcribing")
                    if enabled:
                        play_sound_file_async(path)
                elif new == AppState.LISTENING and old in (
                    AppState.TRANSCRIBING,
                    AppState.INJECTING,
                ):
                    enabled, path = get_sound_for_event(config.audio, "ready")
                    if enabled:
                        play_sound_file_async(path)

            def on_agent_change(self, agent_name: str, index: int) -> None:
                import logging as _logging

                _log = _logging.getLogger(__name__)
                _log.info("on_agent_change: %s (index=%d)", agent_name, index)

                from voxtype.audio.beep import get_sound_for_event

                enabled, _ = get_sound_for_event(config.audio, "agent_announce")
                if not enabled:
                    _log.info("on_agent_change: agent_announce disabled")
                    return
                eng = engine_ref[0]
                if eng:
                    eng.speak_agent(agent_name)
                else:
                    _log.warning("on_agent_change: engine_ref not set")

        # 1. Create logger for engine
        from voxtype import __version__
        from voxtype.logging.jsonl import JSONLLogger, LogLevel, get_default_log_path

        log_level = LogLevel.DEBUG if self._config.verbose else LogLevel.INFO
        log_path = get_default_log_path("engine")
        self._logger = JSONLLogger(
            log_path,
            __version__,
            level=log_level,
            params={
                "mode": mode,
                "output": self._config.output.mode,
                "verbose": self._config.verbose,  # Include text in logs
            },
        )

        # 2. Create engine with logger
        self._engine = create_engine(
            config=self._config,
            events=ControllerEvents(),
            agent_mode=(self._config.output.mode == "agents"),
            hotkey_enabled=True,
            logger=self._logger,
        )
        engine_ref[0] = self._engine

        # 3. Restore saved state BEFORE HTTP server starts.
        #    Sets _last_sse_agent_id so register_agent() picks the right agent
        #    when SSE clients connect. Must happen before agents can register.
        self._engine._restore_state()

        # 4. Start HTTP server early (so StatusPanel can connect during loading)
        from voxtype.core.http_server import OpenVIPServer

        self._http_server = OpenVIPServer(
            self._engine, self,
            self._config.server.host, self._config.server.port,
        )
        self._http_server.start()
        self._engine.set_status_change_callback(
            self._http_server.notify_status_change
        )

        # 5. Initialize engine (load models — HTTP server serves loading progress)
        self._engine.init_components(headless=True)

        # 6. Start engine runtime (audio streaming, hotkey, state controller)
        self._engine.start_runtime(start_listening=start_listening)

        # 7. Create and start keyboard bindings (foreground only)
        if with_bindings:
            self._bindings = KeyboardBindingManager(self, self._config)
            self._bindings.start()

        self._running = True
        logger.info(
            f"AppController started (mode={mode}, listening={start_listening}, "
            f"bindings={with_bindings})"
        )

    def stop(self) -> None:
        """Stop the application."""
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        # Capture and display stats FIRST (before slow engine shutdown)
        stats = self._engine.stats if self._engine else None
        self._display_session_stats(stats)

        # Stop bindings
        if self._bindings:
            self._bindings.stop()
            self._bindings = None

        # Stop HTTP server (before engine, so SSE clients get clean disconnect)
        if self._http_server:
            self._http_server.stop()
            self._http_server = None

        # Stop engine
        if self._engine:
            self._engine.stop()
            self._engine = None

        # Close logger
        if self._logger:
            self._logger.close()
            self._logger = None

        logger.info("AppController stopped")

    def run(self) -> None:
        """Run the engine main loop (blocking).

        Call this after start() to keep the process alive.
        """
        if self._engine:
            self._engine.run()

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        if self._engine:
            self._engine._running = False
        self._shutdown_event.set()

    def wait_for_shutdown(self, timeout: float | None = None) -> bool:
        """Wait for shutdown signal.

        Args:
            timeout: Max seconds to wait, None for forever.

        Returns:
            True if shutdown was signaled, False if timeout.
        """
        return self._shutdown_event.wait(timeout)

    # =========================================================================
    # App Commands (stateful, non-atomic)
    # =========================================================================

    def toggle_listening(self) -> None:
        """Toggle listening on/off.

        Reads current state and calls set_listening with opposite value.
        """
        if not self._engine:
            return

        current = self._engine.is_listening
        self._engine.set_listening(not current)
        logger.debug(f"toggle_listening: {current} -> {not current}")

    def next_agent(self) -> None:
        """Switch to next agent.

        Uses engine's built-in _switch_agent(direction=+1).
        """
        if not self._engine:
            return

        self._engine.switch_agent(1)

    def prev_agent(self) -> None:
        """Switch to previous agent.

        Uses engine's built-in _switch_agent(direction=-1).
        """
        if not self._engine:
            return

        self._engine.switch_agent(-1)

    def switch_to_agent(self, name: str) -> None:
        """Switch to agent by name.

        Args:
            name: Agent name to switch to.
        """
        if not self._engine:
            return

        self._engine.switch_to_agent_by_name(name)

    def switch_to_agent_index(self, index: int) -> None:
        """Switch to agent by index (1-based for user convenience).

        Args:
            index: 1-based agent index.
        """
        if not self._engine:
            return

        # Engine uses 0-based, users use 1-based
        self._engine.switch_to_agent_by_index(index - 1)

    def set_output_mode(self, mode: str) -> None:
        """Switch output mode (keyboard <-> agents).

        Args:
            mode: "keyboard" or "agents".
        """
        if not self._engine:
            return
        self._engine.set_output_mode(mode)

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def engine(self) -> VoxtypeEngine | None:
        """Get the engine instance."""
        return self._engine

    @property
    def config(self) -> Config:
        """Get the configuration."""
        return self._config

    @property
    def is_running(self) -> bool:
        """Check if controller is running."""
        return self._running

    @property
    def is_listening(self) -> bool:
        """Check if engine is listening."""
        return self._engine.is_listening if self._engine else False

    @property
    def current_agent(self) -> str | None:
        """Get current agent name."""
        if not self._engine:
            return None
        return self._engine.current_agent

    @property
    def agents(self) -> list[str]:
        """Get list of agent names."""
        if not self._engine:
            return []
        return self._engine.agents

    # =========================================================================
    # Internal
    # =========================================================================

    def _handle_app_command(self, body: dict) -> dict:
        """Handle application-level control commands.

        Called by engine for commands that are not protocol-level
        (i.e., not stt.*, engine.shutdown, or ping).
        """
        command = body.get("command", "")
        logger.info("app_command: %s", command)

        if command == "output.set_agent" or command.startswith("output.set_agent:"):
            agent = command.split(":", 1)[1] if ":" in command else body.get("agent", "")
            logger.info("switch_to_agent: %s", agent)
            self.switch_to_agent(agent)
            return {"status": "ok"}
        elif command.startswith("output.set_mode:"):
            mode = command.split(":", 1)[1]
            self.set_output_mode(mode)
            return {"status": "ok", "mode": mode}

        return {"status": "error", "error": f"Unknown command: {command}"}

    def _display_session_stats(self, stats: Any = None) -> None:
        """Display session statistics on exit.

        Args:
            stats: SessionStats snapshot captured before engine shutdown.
        """
        import random
        from datetime import datetime

        from rich.columns import Columns
        from rich.console import Console
        from rich.table import Table

        from voxtype.utils.stats import update_stats

        s = stats
        if s is None:
            return

        # Skip if no transcriptions were made
        if s.count == 0:
            return

        console = Console()

        # Average typing speed from config
        typing_wpm = self._config.stats.typing_wpm
        chars_per_minute = typing_wpm * 5

        typing_time_minutes = s.chars / chars_per_minute
        total_voxtype_seconds = (
            s.audio_seconds + s.transcription_seconds + s.injection_seconds
        )
        total_voxtype_minutes = total_voxtype_seconds / 60

        effective_wpm = (
            s.words / total_voxtype_minutes if total_voxtype_minutes > 0 else 0
        )

        time_saved_minutes = typing_time_minutes - total_voxtype_minutes
        time_saved_seconds = time_saved_minutes * 60

        # Update persistent stats
        lifetime = update_stats(
            transcriptions=s.count,
            words=s.words,
            chars=s.chars,
            audio_seconds=s.audio_seconds,
            transcription_seconds=s.transcription_seconds,
            injection_seconds=s.injection_seconds,
            time_saved_seconds=max(0, time_saved_seconds),
        )

        # Create two-column stats layout
        left_table = Table(title="Output", expand=False, show_header=False, box=None)
        left_table.add_column("Metric", style="dim")
        left_table.add_column("Value", style="cyan")
        left_table.add_row("Transcriptions", str(s.count))
        left_table.add_row("Words", str(s.words))
        left_table.add_row("Characters", str(s.chars))
        left_table.add_row("Effective WPM", f"{effective_wpm:.0f}")

        right_table = Table(title="Timing", expand=False, show_header=False, box=None)
        right_table.add_column("Metric", style="dim")
        right_table.add_column("Value", style="cyan")
        right_table.add_row("Audio", f"{s.audio_seconds:.1f}s")
        right_table.add_row("STT", f"{s.transcription_seconds:.1f}s")
        right_table.add_row("Injection", f"{s.injection_seconds:.1f}s")
        right_table.add_row("Processing", f"{total_voxtype_seconds:.1f}s")

        console.print()
        console.print(Columns([left_table, right_table], padding=(0, 4)))

        # Fun phrases for session time saved
        if time_saved_seconds > 0:
            time_saved_phrases = [
                "Saved you [bold]{time}[/]. You're welcome.",
                "[bold]{time}[/] back in your pocket.",
                "Time saved: [bold]{time}[/]. My pleasure!",
                "[bold]{time}[/] extra for coffee.",
                "[bold]{time}[/] gained. Use them wisely!",
            ]

            if time_saved_seconds >= 60:
                time_str = f"{time_saved_minutes:.1f} minutes"
            else:
                time_str = f"{time_saved_seconds:.0f} seconds"

            phrase = random.choice(time_saved_phrases).format(time=time_str)
            console.print()
            console.print(f"[green bold]{phrase}[/]")

        # Lifetime stats line
        lifetime_saved = lifetime["total_time_saved_seconds"]
        if lifetime_saved >= 3600:
            lifetime_time_str = f"{lifetime_saved / 3600:.1f} hours"
        elif lifetime_saved >= 60:
            lifetime_time_str = f"{lifetime_saved / 60:.0f} minutes"
        else:
            lifetime_time_str = f"{lifetime_saved:.0f} seconds"

        sessions_str = (
            f"{lifetime['sessions']} session"
            if lifetime["sessions"] == 1
            else f"{lifetime['sessions']} sessions"
        )
        if lifetime["first_use"]:
            try:
                first_use = datetime.fromisoformat(lifetime["first_use"])
                since_str = first_use.strftime("%b %d, %Y")
                console.print(
                    f"[dim]All time: [green]{lifetime_time_str}[/] saved "
                    f"across {sessions_str} (since {since_str})[/]"
                )
            except ValueError:
                pass
