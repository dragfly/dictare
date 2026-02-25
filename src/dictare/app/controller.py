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

import atexit
import errno
import logging
import os
import sys
import threading
from typing import TYPE_CHECKING, Any

from dictare.core.events import EngineEvents

if TYPE_CHECKING:
    from dictare.app.bindings import KeyboardBindingManager
    from dictare.config import Config
    from dictare.core.engine import DictareEngine

logger = logging.getLogger(__name__)


class _ControllerEvents(EngineEvents):
    """Event handler for audio feedback during engine state changes.

    Plays start/stop sounds, typewriter loop during transcription,
    and announces agent switches via TTS.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._engine_ref: DictareEngine | None = None

    def set_engine(self, engine: DictareEngine) -> None:
        """Wire the engine reference (called after engine creation)."""
        self._engine_ref = engine

    def on_state_change(self, old: Any, new: Any, trigger: str) -> None:
        from dictare.audio.beep import (
            get_sound_for_event,
            is_looping,
            play_audio,
            play_sound_file_async,
            start_loop,
            stop_loop,
        )
        from dictare.core.fsm import AppState

        config = self._config
        eng = self._engine_ref
        ctrl = eng._controller if eng else None
        pause = not config.audio.headphones_mode

        # Check loop state before stopping — used to gate the ready sound.
        was_looping = old == AppState.TRANSCRIBING and is_looping()

        # Stop any active loop whenever we leave TRANSCRIBING
        if old == AppState.TRANSCRIBING:
            stop_loop()

        if new == AppState.LISTENING and old == AppState.OFF:
            enabled, path = get_sound_for_event(config.audio, "start")
            if enabled:
                play_audio(path, pause_mic=pause, controller=ctrl)
        elif new == AppState.OFF:
            enabled, path = get_sound_for_event(config.audio, "stop")
            if enabled:
                play_audio(path, pause_mic=False)
        elif new == AppState.TRANSCRIBING:
            # Only play typewriter loop for long recordings (>= 8 s of audio).
            audio_ms = 0.0
            if trigger.startswith("speech_end:"):
                try:
                    audio_ms = float(trigger.split(":", 1)[1])
                except ValueError:
                    pass
            if audio_ms >= config.audio.advanced.transcribing_sound_min_ms:
                enabled, path = get_sound_for_event(config.audio, "transcribing")
                if enabled:
                    scfg = config.audio.sounds.get("transcribing")
                    vol = scfg.volume if scfg is not None else 1.0
                    start_loop(path, volume=vol)
        elif new == AppState.LISTENING and old in (
            AppState.TRANSCRIBING,
            AppState.INJECTING,
        ):
            # Only play carriage-return if typewriter was playing.
            if was_looping:
                enabled, path = get_sound_for_event(config.audio, "ready")
                if enabled:
                    scfg = config.audio.sounds.get("ready")
                    vol = scfg.volume if scfg is not None else 1.0
                    play_sound_file_async(path, volume=vol)

    def on_agent_change(self, agent_name: str, index: int) -> None:
        logger.info("on_agent_change: %s (index=%d)", agent_name, index)

        from dictare.audio.beep import get_sound_for_event

        enabled, _ = get_sound_for_event(self._config.audio, "agent_announce")
        if not enabled:
            logger.info("on_agent_change: agent_announce disabled")
            return
        eng = self._engine_ref
        if eng:
            eng.speak_agent(agent_name)
        else:
            logger.warning("on_agent_change: engine_ref not set")


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
        self._engine: DictareEngine | None = None
        self._http_server: Any = None  # OpenVIPServer
        self._bindings: KeyboardBindingManager | None = None
        self._logger: Any = None  # JSONLLogger
        self._running = False
        self._shutdown_event = threading.Event()

    # =========================================================================
    # Single-instance enforcement
    # =========================================================================

    def _check_single_instance(self) -> None:
        """Fail fast if another engine instance is already running.

        Uses a PID file at ~/.dictare/engine.pid.  Stale files (process gone)
        are silently removed; live processes cause a RuntimeError.
        """
        from dictare.utils.paths import get_dictare_dir, get_pid_path

        pid_path = get_pid_path()

        if pid_path.exists():
            try:
                existing_pid = int(pid_path.read_text().strip())
                try:
                    os.kill(existing_pid, 0)  # Signal 0 = existence check
                    # Process exists — refuse to start
                    raise RuntimeError(
                        f"Dictare engine already running (PID {existing_pid}).\n"
                        "Stop it first:\n"
                        "  dictare service stop"
                    )
                except ProcessLookupError:
                    # Stale PID — process no longer exists
                    logger.info("Stale engine PID file (PID %d not running), removing", existing_pid)
                    pid_path.unlink(missing_ok=True)
            except (ValueError, OSError):
                # Unreadable or corrupt PID file — ignore and overwrite
                pass

        # Write our PID
        get_dictare_dir().mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()))
        atexit.register(self._cleanup_pid)
        logger.info("Engine PID file written: %s (PID %d)", pid_path, os.getpid())

    def _cleanup_pid(self) -> None:
        """Remove the PID file on exit (only if it contains our PID)."""
        from dictare.utils.paths import get_pid_path

        try:
            pid_path = get_pid_path()
            if pid_path.exists() and pid_path.read_text().strip() == str(os.getpid()):
                pid_path.unlink()
        except OSError:
            pass

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
        # 0. Single-instance check — fail fast before creating any resources
        self._check_single_instance()

        from dictare.app.bindings import KeyboardBindingManager
        from dictare.core.engine import create_engine

        events = _ControllerEvents(self._config)

        # 1. Create logger for engine
        from dictare import __version__
        from dictare.logging.jsonl import JSONLLogger, LogLevel, get_default_log_path

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
        # macOS serve mode: Swift launcher handles hotkey via CGEventTap + SIGUSR1,
        #   so disable engine's pynput listener to avoid double toggle.
        # Linux serve mode: no Swift launcher — engine must listen for hotkey
        #   directly via evdev.
        enable_hotkey = with_bindings or sys.platform != "darwin"
        logger.info(
            "AppController.start: config.output.mode=%r, with_bindings=%r, "
            "enable_hotkey=%r, platform=%r, start_listening=%r",
            self._config.output.mode, with_bindings, enable_hotkey,
            sys.platform, start_listening,
        )
        self._engine = create_engine(
            config=self._config,
            events=events,
            hotkey_enabled=enable_hotkey,
            logger=self._logger,
        )
        events.set_engine(self._engine)

        # 3. Restore saved state BEFORE HTTP server starts.
        #    Overrides config defaults with saved session if fresh.
        start_listening = self._engine._restore_state(start_listening)

        # 4. Start HTTP server early (so StatusPanel can connect during loading)
        from dictare.core.http_server import OpenVIPServer

        self._http_server = OpenVIPServer(
            self._engine, self,
            self._config.server.host, self._config.server.port,
            auth_tokens={"register_tts": self._engine._tts_mgr.auth_token},
        )
        self._http_server.start()

        # Hard fail if port is already in use — engine must not run without HTTP server.
        # Without this check, the engine would start, grab the microphone, and process
        # audio with no way to receive agent connections (dual-instance silent failure).
        if not self._http_server.wait_started(timeout=5.0):
            err = getattr(self._http_server, "_start_error", None)
            self._cleanup_pid()
            if isinstance(err, OSError) and getattr(err, "errno", None) == errno.EADDRINUSE:
                raise RuntimeError(
                    f"Port {self._config.server.port} already in use — "
                    "another engine instance is running.\n"
                    "Stop it first:\n"
                    "  dictare engine stop\n"
                    "  # or: dictare service stop"
                )
            raise RuntimeError(f"HTTP server failed to start: {err}")

        self._engine.set_status_change_callback(
            self._http_server.notify_status_change
        )

        # 5. Initialize engine (load models — HTTP server serves loading progress)
        self._engine.init_components(
            headless=True, http_server=self._http_server,
        )

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
        self._cleanup_pid()

        # Capture and display stats FIRST (before slow engine shutdown)
        stats = self._engine.stats if self._engine else None
        self._display_session_stats(stats)

        # Save final state, then disable further saves — agents unregister during
        # HTTP server shutdown and would overwrite state with stale data.
        if self._engine:
            self._engine._save_state()
            self._engine._running = False

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
        """Request graceful shutdown.  Saves session state before stopping."""
        if self._engine:
            self._engine.save_session_before_shutdown()
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

    def on_hotkey_tap(self) -> None:
        """Simulate a complete hotkey tap through the TapDetector.

        Used by SIGUSR1 handler (macOS Swift launcher) to feed taps into
        the same state machine that the pynput/evdev listener uses.
        This gives double-tap detection for free: two SIGUSR1 within 0.4s
        triggers mode switch (agents <-> keyboard).
        """
        if not self._engine:
            return
        self._engine._tap_detector.on_key_down()
        self._engine._tap_detector.on_key_up()

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

        If the engine is in keyboard mode, switches to agents mode first
        so the voice output actually reaches the agent.

        Args:
            name: Agent name to switch to.
        """
        if not self._engine:
            return

        if not self._engine.agent_mode:
            self._engine.set_output_mode("agents")

        self._engine.switch_to_agent_by_name(name)

    def switch_to_agent_index(self, index: int) -> None:
        """Switch to agent by index (1-based for user convenience).

        Args:
            index: 1-based agent index.
        """
        if not self._engine:
            return

        self._engine.switch_to_agent_by_index(index)

    def repeat_last(self) -> None:
        """Resend the last transcription to the current agent."""
        if not self._engine:
            return

        self._engine.resend_last()

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
    def engine(self) -> DictareEngine | None:
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

        from dictare.utils.stats import update_stats

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
        total_dictare_seconds = (
            s.audio_seconds + s.transcription_seconds + s.injection_seconds
        )
        total_dictare_minutes = total_dictare_seconds / 60

        effective_wpm = (
            s.words / total_dictare_minutes if total_dictare_minutes > 0 else 0
        )

        time_saved_minutes = typing_time_minutes - total_dictare_minutes
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
        right_table.add_row("Processing", f"{total_dictare_seconds:.1f}s")

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
