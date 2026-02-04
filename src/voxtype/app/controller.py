"""AppController - application-level logic and user interaction.

The AppController is the central coordinator for foreground mode (CLI and Tray).
It creates and manages:
- Engine (STT, VAD, audio)
- Adapter (HTTP server for OpenVIP)
- KeyboardBindingManager (hotkeys, shortcuts, device profiles)
- Agent Registrar (agent discovery)

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
    from voxtype.adapters.openvip import OpenVIPAdapter
    from voxtype.app.bindings import KeyboardBindingManager
    from voxtype.config import Config
    from voxtype.core.engine import VoxtypeEngine

logger = logging.getLogger(__name__)

class AppController:
    """Application controller for foreground mode.

    Manages the lifecycle of engine, adapter, and input bindings.
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
        self._adapter: OpenVIPAdapter | None = None
        self._registrar: Any = None  # AgentRegistrar
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
        1. Engine (loads models)
        2. Adapter (HTTP server)
        3. KeyboardBindingManager (hotkeys, shortcuts) - if with_bindings=True
        4. Agent Registrar (if agent mode)

        Args:
            start_listening: If True, start listening immediately.
            mode: "foreground" or "daemon".
            with_bindings: If True, start keyboard bindings (foreground only).
        """
        from voxtype.adapters.openvip import OpenVIPAdapter
        from voxtype.app.bindings import KeyboardBindingManager
        from voxtype.core.engine import create_engine
        from voxtype.core.events import EngineEvents

        # Create event handler that updates adapter state
        adapter_ref: list[OpenVIPAdapter | None] = [None]
        engine_ref: list[VoxtypeEngine | None] = [None]
        config = self._config  # Capture for closure

        class ControllerEvents(EngineEvents):
            """Event handler that forwards events to adapter."""

            def on_vad_loading(self) -> None:
                if adapter_ref[0]:
                    adapter_ref[0]._update_loading("stt", "done")
                    adapter_ref[0]._update_loading("vad", "loading")

            def on_transcription(self, result: Any) -> None:
                if adapter_ref[0] and hasattr(result, "text"):
                    adapter_ref[0].state.stt.last_text = result.text

            def on_state_change(self, old: Any, new: Any, trigger: str) -> None:
                from voxtype.core.state import AppState

                if adapter_ref[0]:
                    if new == AppState.LISTENING:
                        adapter_ref[0].state.stt.state = "listening"
                    elif new == AppState.OFF:
                        adapter_ref[0].state.stt.state = "idle"
                    elif new == AppState.RECORDING:
                        adapter_ref[0].state.stt.state = "recording"
                    elif new == AppState.TRANSCRIBING:
                        adapter_ref[0].state.stt.state = "transcribing"

                # Play beep if audio feedback enabled
                # Only beep on OFF → LISTENING, not TRANSCRIBING → LISTENING
                if config.audio.audio_feedback:
                    from voxtype.audio.beep import (
                        DEFAULT_SOUND_START,
                        DEFAULT_SOUND_STOP,
                        play_sound_file,
                        play_sound_file_async,
                    )
                    from voxtype.core.events import TTSCompleteEvent, TTSStartEvent

                    if new == AppState.LISTENING and old == AppState.OFF:
                        path = config.audio.sound_start or str(DEFAULT_SOUND_START)
                        eng = engine_ref[0]
                        if eng and not config.audio.headphones_mode:
                            tts_id = eng._controller.get_next_tts_id()
                            eng._controller.send(TTSStartEvent(text="", source="audio"))

                            def _play_start(tid: int = tts_id, p: str = path) -> None:
                                try:
                                    play_sound_file(p)
                                finally:
                                    eng._controller.send(
                                        TTSCompleteEvent(tts_id=tid, source="audio")
                                    )

                            threading.Thread(
                                target=_play_start, daemon=True
                            ).start()
                        else:
                            play_sound_file_async(path)
                    elif new == AppState.OFF:
                        path = config.audio.sound_stop or str(DEFAULT_SOUND_STOP)
                        play_sound_file_async(path)

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
        self._engine, self._registrar = create_engine(
            config=self._config,
            events=ControllerEvents(),
            agent_mode=(self._config.output.mode == "agents"),
            hotkey_enabled=True,
            logger=self._logger,
        )
        engine_ref[0] = self._engine

        # 2. Create adapter
        self._adapter = OpenVIPAdapter(self._engine, self._config)
        adapter_ref[0] = self._adapter

        # 3. Start adapter (HTTP server)
        self._adapter.state.mode = mode
        self._adapter.start()

        # 4. Setup loading state for progress tracking
        self._adapter.setup_loading_state()

        # 5. Initialize engine (load models)
        self._engine.init_components(headless=True)

        # 6. Start engine runtime
        self._engine.start_runtime(start_listening=start_listening)

        # 7. Mark loading complete
        self._adapter.mark_loading_complete()
        self._adapter.update_engine_state(
            listening=start_listening,
            hotkey_bound=self._engine._hotkey is not None,
        )

        # 8. Start agent registrar
        if self._registrar:
            self._registrar.start()

        # 9. Create and start keyboard bindings (foreground only)
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

        # Stop bindings
        if self._bindings:
            self._bindings.stop()
            self._bindings = None

        # Stop registrar
        if self._registrar:
            self._registrar.stop()
            self._registrar = None

        # Stop adapter (stops engine too)
        if self._adapter:
            self._adapter.stop()
            self._adapter = None

        self._engine = None

        # Close logger
        if self._logger:
            self._logger.close()
            self._logger = None

        # Display session stats
        self._display_session_stats()

        logger.info("AppController stopped")

    def run(self) -> None:
        """Run the adapter main loop (blocking).

        Call this after start() to keep the process alive.
        """
        if self._adapter:
            self._adapter.run(start_listening=False)

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        if self._adapter:
            self._adapter.request_shutdown()
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
        self._engine._set_listening(not current)
        logger.debug(f"toggle_listening: {current} -> {not current}")

    def next_agent(self) -> None:
        """Switch to next agent.

        Uses engine's built-in _switch_agent(direction=+1).
        """
        if not self._engine:
            return

        self._engine._switch_agent(1)

    def prev_agent(self) -> None:
        """Switch to previous agent.

        Uses engine's built-in _switch_agent(direction=-1).
        """
        if not self._engine:
            return

        self._engine._switch_agent(-1)

    def switch_to_agent(self, name: str) -> None:
        """Switch to agent by name.

        Args:
            name: Agent name to switch to.
        """
        if not self._engine:
            return

        self._engine._switch_to_agent_by_name(name)

    def switch_to_agent_index(self, index: int) -> None:
        """Switch to agent by index (1-based for user convenience).

        Args:
            index: 1-based agent index.
        """
        if not self._engine:
            return

        # Engine uses 0-based, users use 1-based
        self._engine._switch_to_agent_by_index(index - 1)

    def _announce_agent(self, agent_name: str) -> None:
        """Announce agent change via TTS."""
        # TODO: Implement TTS announcement
        # This should use engine TTS when implemented
        pass

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def engine(self) -> VoxtypeEngine | None:
        """Get the engine instance."""
        return self._engine

    @property
    def adapter(self) -> OpenVIPAdapter | None:
        """Get the adapter instance."""
        return self._adapter

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

    def _display_session_stats(self) -> None:
        """Display session statistics on exit."""
        import random
        from datetime import datetime

        from rich.columns import Columns
        from rich.console import Console
        from rich.table import Table

        from voxtype.utils.stats import update_stats

        if not self._engine:
            return

        # Skip if no transcriptions were made
        if self._engine.stats_count == 0:
            return

        console = Console()

        # Get stats from engine
        stats_count = self._engine.stats_count
        stats_chars = self._engine.stats_chars
        stats_words = self._engine.stats_words
        stats_audio_seconds = self._engine.stats_audio_seconds
        stats_transcription_seconds = self._engine.stats_transcription_seconds
        stats_injection_seconds = self._engine.stats_injection_seconds

        # Average typing speed from config
        typing_wpm = self._config.stats.typing_wpm
        chars_per_minute = typing_wpm * 5

        typing_time_minutes = stats_chars / chars_per_minute
        total_voxtype_seconds = (
            stats_audio_seconds + stats_transcription_seconds + stats_injection_seconds
        )
        total_voxtype_minutes = total_voxtype_seconds / 60

        effective_wpm = (
            stats_words / total_voxtype_minutes if total_voxtype_minutes > 0 else 0
        )

        time_saved_minutes = typing_time_minutes - total_voxtype_minutes
        time_saved_seconds = time_saved_minutes * 60

        # Update persistent stats
        lifetime = update_stats(
            transcriptions=stats_count,
            words=stats_words,
            chars=stats_chars,
            audio_seconds=stats_audio_seconds,
            transcription_seconds=stats_transcription_seconds,
            injection_seconds=stats_injection_seconds,
            time_saved_seconds=max(0, time_saved_seconds),
        )

        # Create two-column stats layout
        left_table = Table(title="Output", expand=False, show_header=False, box=None)
        left_table.add_column("Metric", style="dim")
        left_table.add_column("Value", style="cyan")
        left_table.add_row("Transcriptions", str(stats_count))
        left_table.add_row("Words", str(stats_words))
        left_table.add_row("Characters", str(stats_chars))
        left_table.add_row("Effective WPM", f"{effective_wpm:.0f}")

        right_table = Table(title="Timing", expand=False, show_header=False, box=None)
        right_table.add_column("Metric", style="dim")
        right_table.add_column("Value", style="cyan")
        right_table.add_row("Audio", f"{stats_audio_seconds:.1f}s")
        right_table.add_row("STT", f"{stats_transcription_seconds:.1f}s")
        right_table.add_row("Injection", f"{stats_injection_seconds:.1f}s")
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
