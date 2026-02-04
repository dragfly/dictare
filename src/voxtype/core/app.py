"""Main application orchestrator with UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

from voxtype.core.events import EngineEvents, InjectionResult, TranscriptionResult
from voxtype.core.messages import create_message
from voxtype.core.state import AppState

if TYPE_CHECKING:
    from voxtype.config import Config
    from voxtype.logging.jsonl import JSONLLogger
    from voxtype.output.sse import SSEServer
    from voxtype.ui.status import LiveStatusPanel

class VoxtypeApp(EngineEvents):
    """Main application orchestrator with UI.

    This is a thin wrapper over VoxtypeEngine that adds:
    - Console output (rich)
    - Status panel updates
    - Audio feedback (beeps)
    - TTS announcements
    - Session statistics display

    Implements EngineEvents to receive callbacks from the engine.
    """

    def __init__(
        self,
        config: Config,
        logger: JSONLLogger | None = None,
        agent_mode: bool = False,
        realtime: bool = False,
    ) -> None:
        """Initialize the application.

        Args:
            config: Application configuration.
            logger: Optional JSONL logger for structured logging.
            agent_mode: Enable agent mode (output to agents instead of keyboard).
            realtime: Enable realtime transcription feedback while speaking.
        """
        self.config = config
        self._realtime = realtime
        self._console = Console(
            force_terminal=None,
            force_interactive=None,
            legacy_windows=False,
            safe_box=True,
        )

        # Live status panel (set in run())
        self._status_panel: LiveStatusPanel | None = None

        # HTTP/SSE server (set in run() if configured)
        self._sse: SSEServer | None = None

        # Use shared initialization logic (same as daemon)
        from voxtype.core.engine import create_engine

        self._engine = create_engine(
            config=config,
            events=self,
            logger=logger,
            agent_mode=agent_mode,
            realtime=realtime,
        )

    # -------------------------------------------------------------------------
    # Delegate Properties to Engine
    # -------------------------------------------------------------------------

    @property
    def state(self) -> AppState:
        """Get current application state."""
        return self._engine.state

    @property
    def is_listening(self) -> bool:
        """Check if in LISTENING state."""
        return self._engine.is_listening

    @property
    def is_off(self) -> bool:
        """Check if in OFF state."""
        return self._engine.is_off

    @property
    def current_agent(self) -> str | None:
        """Get the name of the current agent."""
        return self._engine.current_agent

    # -------------------------------------------------------------------------
    # EngineEvents Implementation (UI callbacks)
    # -------------------------------------------------------------------------

    def on_engine_ready(self) -> None:
        """Handle engine ready event."""
        # Engine is ready - could show notification or update status
        return None

    def on_state_change(
        self, old: AppState, new: AppState, trigger: str
    ) -> None:
        """Handle engine state changes with UI feedback."""
        # Update status panel
        if self._status_panel:
            self._status_panel.update_state(new.name)

        # Send to SSE if running
        if self._sse:
            self._sse.send_state_change(old, new, trigger)

        # Play audio feedback
        if new == AppState.LISTENING and old == AppState.OFF:
            self._play_feedback("listening_on")
        elif new == AppState.OFF and old == AppState.LISTENING:
            self._play_feedback("listening_off")

    def on_transcription(self, result: TranscriptionResult) -> None:
        """Handle transcription completion."""
        # Note: verbose debug and realtime text go to status panel
        # Don't print here - it corrupts the Live panel

        # Send to SSE if running
        if self._sse:
            msg = create_message(result.text)
            self._sse.send_message(msg)

    def on_injection(self, result: InjectionResult) -> None:
        """Handle text injection completion."""
        # Update status panel with the text
        if self._status_panel:
            self._status_panel.update_text(result.text)
        # Note: verbose injection debug removed - corrupts Live panel

        if not result.success:
            # Show graceful error message (e.g., "<agent 'claude' not running>")
            error_text = result.error or "Injection failed"
            if self._status_panel:
                self._status_panel.update_text(error_text, is_error=True)
            else:
                self._console.print(f"[bold yellow on red] {error_text} [/]")

        # Beep when file write succeeds
        if result.success and result.method.startswith("file:"):
            from voxtype.audio.beep import play_beep_sent
            play_beep_sent()

    def on_agent_change(self, agent_name: str, index: int) -> None:
        """Handle agent change."""
        # Update panel to highlight current agent (don't print - breaks Live display)
        if self._status_panel:
            self._status_panel.update_current_agent(agent_name, index)

        # Send to SSE if running
        if self._sse:
            self._sse.send_agent_change(agent_name, index)

        self._speak_agent(agent_name)

    def on_agents_changed(self, agents: list[str]) -> None:
        """Handle agents list change (auto-discovery)."""
        if self._status_panel:
            self._status_panel.update_agents(agents)

    def on_error(self, message: str, context: str) -> None:
        """Handle errors."""
        if self.config.verbose:
            # Show in panel if active, otherwise print
            if self._status_panel:
                self._status_panel.update_text(f"[ERROR] {context}: {message}")
            else:
                self._console.print(f"[red]Error in {context}: {message}[/]")

        # Send to SSE if running
        if self._sse:
            self._sse.send_error(message, context)

    def on_partial_transcription(self, text: str) -> None:
        """Handle partial transcription (realtime mode)."""
        # Update panel instead of printing (prevents breaking Rich Live)
        if self._status_panel:
            self._status_panel.update_partial(text)

        # Send to SSE if running
        if self._sse:
            self._sse.send_partial_transcription(text)

    def on_recording_start(self) -> None:
        """Handle recording start."""
        if self._status_panel:
            self._status_panel.update_state("RECORDING")
        # Note: verbose debug removed - corrupts Live panel

    def on_recording_end(self, duration_ms: float) -> None:
        """Handle recording end."""
        if self._status_panel:
            self._status_panel.update_state("TRANSCRIBING")

    def on_max_duration_reached(self) -> None:
        """Handle max speech duration reached."""
        # Note: Don't print here - it corrupts the Live panel
        # The beep provides audio feedback instead
        if self.config.audio.audio_feedback:
            from voxtype.audio.beep import play_beep_sent
            play_beep_sent()

    def on_vad_loading(self) -> None:
        """Handle VAD model loading start.

        Note: Loading indicator is now shown by load_with_indicator().
        """
        pass

    def on_device_reconnect_attempt(self, attempt: int) -> None:
        """Handle device reconnection attempt."""
        # Update status panel instead of printing (prevents breaking Rich Live)
        if self._status_panel:
            self._status_panel.update_text(f"Reconnecting... (attempt {attempt})")

    def on_device_reconnect_success(self, device_name: str | None) -> None:
        """Handle device reconnection success."""
        # Update status panel instead of printing
        if self._status_panel:
            msg = f"Reconnected: {device_name}" if device_name else "Reconnected"
            self._status_panel.update_text(msg)

    # -------------------------------------------------------------------------
    # Delegate Methods to Engine (for AppCommands compatibility)
    # -------------------------------------------------------------------------

    def _toggle_listening(self) -> None:
        """Toggle listening on/off."""
        self._engine._toggle_listening()

    def _set_listening(self, on: bool) -> None:
        """Set listening state on/off."""
        self._engine._set_listening(on)

    def _switch_agent(self, direction: int) -> None:
        """Switch to next/previous agent."""
        self._engine._switch_agent(direction)

    def _switch_to_agent_by_name(self, name: str) -> bool:
        """Switch to a specific agent by name."""
        return self._engine._switch_to_agent_by_name(name)

    def _switch_to_agent_by_index(self, index: int) -> bool:
        """Switch to a specific agent by index (1-based)."""
        return self._engine._switch_to_agent_by_index(index)

    def _send_submit(self) -> None:
        """Send submit (Enter key) to the target."""
        self._engine._send_submit()
        # Update status panel instead of printing
        if self._status_panel:
            self._status_panel.update_text("[Submit sent]")

    def _discard_current(self) -> None:
        """Discard current recording/transcription."""
        self._engine._discard_current()
        if self._status_panel:
            self._status_panel.update_state("LISTENING")

    # -------------------------------------------------------------------------
    # UI-Only Methods
    # -------------------------------------------------------------------------

    def _speak_text(self, text: str) -> None:
        """Speak text using TTS - delegates to engine."""
        self._engine.speak_text(text)

    def _speak_agent(self, agent_name: str) -> None:
        """Speak agent name using TTS - delegates to engine."""
        self._engine.speak_agent(agent_name)

    def _play_feedback(self, event: str) -> None:
        """Play audio feedback for state changes."""
        if not self.config.audio.audio_feedback:
            return

        from voxtype.audio.beep import DEFAULT_SOUND_START, DEFAULT_SOUND_STOP, play_audio

        pause = not self.config.audio.headphones_mode
        ctrl = self._engine._controller

        if event == "listening_on":
            path = self.config.audio.sound_start or str(DEFAULT_SOUND_START)
            play_audio(path, pause_mic=pause, controller=ctrl)
        elif event == "listening_off":
            path = self.config.audio.sound_stop or str(DEFAULT_SOUND_STOP)
            play_audio(path, pause_mic=False)

    def _display_session_stats(self) -> None:
        """Display session statistics on exit."""
        import random
        from datetime import datetime

        try:
            from rich.columns import Columns
            from rich.table import Table
        except ImportError:
            # Fallback if rich modules not available during cleanup
            return

        from voxtype.utils.stats import update_stats

        # Skip if no transcriptions were made
        s = self._engine.stats
        if s.count == 0:
            return

        # Average typing speed from config
        typing_wpm = self.config.stats.typing_wpm
        chars_per_minute = typing_wpm * 5

        typing_time_minutes = s.chars / chars_per_minute
        total_voxtype_seconds = (
            s.audio_seconds
            + s.transcription_seconds
            + s.injection_seconds
        )
        total_voxtype_minutes = total_voxtype_seconds / 60

        effective_wpm = s.words / total_voxtype_minutes if total_voxtype_minutes > 0 else 0

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

        self._console.print()
        self._console.print(Columns([left_table, right_table], padding=(0, 4)))

        # Fun phrases for session time saved
        if time_saved_seconds > 0:
            time_saved_phrases = [
                "Saved you [bold]{time}[/]. You're welcome.",
                "[bold]{time}[/] back in your pocket.",
                "Time saved: [bold]{time}[/]. My pleasure!",
                "[bold]{time}[/] extra for coffee.",
                "[bold]{time}[/] gained. Use them wisely!",
                "[bold]{time}[/] freed up. Maybe call someone who'd love to hear from you?",
                "[bold]{time}[/] saved. Pay it forward.",
                "[bold]{time}[/] reclaimed. Go make someone's day.",
                "[bold]{time}[/] in your hands. Spend them on something that matters.",
                "[bold]{time}[/] unlocked. Perfect for a random act of kindness.",
            ]

            if time_saved_seconds >= 60:
                time_str = f"{time_saved_minutes:.1f} minutes"
            else:
                time_str = f"{time_saved_seconds:.0f} seconds"

            phrase = random.choice(time_saved_phrases).format(time=time_str)
            self._console.print()
            self._console.print(f"[green bold]{phrase}[/]")

        # Lifetime stats line
        lifetime_saved = lifetime["total_time_saved_seconds"]
        if lifetime_saved >= 3600:
            lifetime_time_str = f"{lifetime_saved / 3600:.1f} hours"
        elif lifetime_saved >= 60:
            lifetime_time_str = f"{lifetime_saved / 60:.0f} minutes"
        else:
            lifetime_time_str = f"{lifetime_saved:.0f} seconds"

        sessions_str = f"{lifetime['sessions']} session" if lifetime['sessions'] == 1 else f"{lifetime['sessions']} sessions"
        if lifetime["first_use"]:
            try:
                first_use = datetime.fromisoformat(lifetime["first_use"])
                since_str = first_use.strftime("%b %d, %Y")
                self._console.print(
                    f"[dim]All time: [green]{lifetime_time_str}[/] saved across {sessions_str} (since {since_str})[/]"
                )
            except ValueError:
                self._console.print(
                    f"[dim]All time: [green]{lifetime_time_str}[/] saved across {sessions_str}[/]"
                )
        else:
            self._console.print(
                f"[dim]All time: [green]{lifetime_time_str}[/] saved across {sessions_str}[/]"
            )
        self._console.print()

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def run(self, status_panel: LiveStatusPanel | None = None) -> None:
        """Start the application main loop."""
        self._status_panel = status_panel
        self._run_vad_mode()

    def _run_vad_mode(self) -> None:
        """Run in VAD (voice activity detection) mode."""
        # Initialize engine components (STT and VAD loading happens here with progress indicators)
        self._engine.init_components()

        # Show hotkey info
        if self.config.verbose and self._engine._hotkey:
            self._console.print(f"[dim]Toggle hotkey: {self._engine._hotkey.get_key_name()}[/]")

        # Note: agent sockets are printed after watcher starts (see below)

        # Initialize HTTP/SSE server if enabled
        if self.config.server.enabled:
            from voxtype.output.sse import SSEServer

            self._sse = SSEServer(
                host=self.config.server.host,
                port=self.config.server.port,
                agent=self._engine.current_agent,
            )
            self._sse.start()
            self._console.print(f"[dim]Server: {self._sse.url}[/]")

        # Initialize input manager
        self._init_input_manager()

        # Pre-warm audio feedback
        if self.config.audio.audio_feedback:
            from voxtype.audio.beep import warmup_audio
            warmup_audio()

        self._engine._running = True
        self._engine._stats_start_time = __import__("time").time()

        # Update status panel with agents (if any connected via SSE)
        if self._engine.agents:
            if self._status_panel:
                self._status_panel.update_agents(self._engine.agents)
        else:
            # Keyboard mode - start the KeyboardAgent
            if self._engine._keyboard_agent:
                self._engine._keyboard_agent.start()
            if self.config.verbose:
                self._console.print("[dim]Output: keyboard (local)[/]")

        # Start the state controller (event queue processor)
        self._engine._controller.start()

        # Start live status panel
        if self._status_panel:
            self._status_panel.start()

        try:
            # Start hotkey listener (tap detector handles single/double tap)
            if self._engine._hotkey:
                self._engine._hotkey.start(
                    on_press=self._engine._tap_detector.on_key_down,
                    on_release=self._engine._tap_detector.on_key_up,
                    on_other_key=self._engine._tap_detector.on_other_key,
                )

            # Transition OFF → LISTENING (startup is special - direct transition OK)
            self._engine._state_manager.transition(AppState.LISTENING)
            if self._status_panel:
                self._status_panel.update_state("LISTENING")

            if self._engine._audio_manager:
                self._engine._audio_manager.start_streaming(
                    should_process=lambda: self._engine._state_manager.should_process_audio,
                    is_running=lambda: self._engine._running,
                )

            # Keep main thread alive
            while self._engine._running:
                __import__("time").sleep(0.1)
                if self._engine._audio_manager and self._engine._audio_manager.needs_reconnect():
                    if not self._engine._audio_manager.reconnect(self._engine._audio_manager._on_audio_chunk):
                        break
        except KeyboardInterrupt:
            pass

    def _init_input_manager(self) -> None:
        """Initialize input manager for keyboard shortcuts and device profiles."""
        from voxtype.commands.app_commands import AppCommands
        from voxtype.input.manager import InputManager

        app_commands = AppCommands(self)

        self._engine._input_manager = InputManager(
            app_commands=app_commands,
            verbose=self.config.verbose,
        )

        if self.config.keyboard.shortcuts:
            self._engine._input_manager.load_keyboard_shortcuts(self.config.keyboard.shortcuts)

        self._engine._input_manager.load_device_profiles()
        self._engine._input_manager.start()

        if self.config.verbose and self._engine._input_manager.running_sources:
            self._console.print(f"[dim]Input sources: {', '.join(self._engine._input_manager.running_sources)}[/]")

    def stop(self) -> None:
        """Stop the application."""
        # Stop status panel FIRST to prevent duplicate rendering
        if self._status_panel:
            self._status_panel.stop()
            self._status_panel = None

        # Stop SSE server
        if self._sse:
            self._sse.stop()
            self._sse = None

        # Note: KeyboardAgent lifecycle is managed by engine.stop()

        # Stop engine
        self._engine.stop()

        # Show session stats
        self._display_session_stats()
