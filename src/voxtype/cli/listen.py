"""Listen command — start foreground voice-to-text."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from voxtype.cli._helpers import (
    apply_cli_overrides,
    auto_detect_acceleration,
    console,
    create_logger,
)
from voxtype.cli.models import check_required_models


def register(app: typer.Typer) -> None:
    """Register listen command on the main app."""

    @app.command()
    def listen(
        # Config file
        config_file: Annotated[
            Path | None,
            typer.Option("--config", "-c", help="Path to config file"),
        ] = None,
        # STT options
        model: Annotated[
            str | None,
            typer.Option("--model", "-m", help="Whisper model (tiny/base/small/medium/large-v3)"),
        ] = None,
        language: Annotated[
            str | None,
            typer.Option("--language", "-l", help="Language code or 'auto'"),
        ] = None,
        no_hw_accel: Annotated[
            bool,
            typer.Option("--no-hw-accel", help="Disable hardware acceleration (force CPU)"),
        ] = False,
        # Input options
        silence_ms: Annotated[
            int | None,
            typer.Option("--silence-ms", "-s", help="VAD silence duration to end speech (ms)"),
        ] = None,
        hotkey: Annotated[
            str | None,
            typer.Option("--hotkey", "-k", help="Toggle listening key (default: SCROLLLOCK)"),
        ] = None,
        max_duration: Annotated[
            int | None,
            typer.Option("--max-duration", help="Max recording duration in seconds"),
        ] = None,
        # Output options (one required)
        keyboard: Annotated[
            bool,
            typer.Option("--keyboard", "-K", help="Keyboard mode - types what you say"),
        ] = False,
        agents: Annotated[
            bool,
            typer.Option("--agents", "-A", help="Agent mode - starts HTTP server, agents connect via SSE"),
        ] = False,
        typing_delay: Annotated[
            int | None,
            typer.Option("--typing-delay", help="Delay between keystrokes in ms"),
        ] = None,
        auto_enter: Annotated[
            bool,
            typer.Option("--auto-enter", help="Press Enter after typing to submit"),
        ] = False,
        # Debug/logging options
        verbose: Annotated[
            bool | None,
            typer.Option("--verbose", "-v", help="Verbose output: device info, transcriptions, debug"),
        ] = None,
        log_file: Annotated[
            str | None,
            typer.Option("--log-file", "-L", help="JSONL log file path"),
        ] = None,
        no_audio_feedback: Annotated[
            bool,
            typer.Option("--no-audio-feedback", help="Disable beep sounds"),
        ] = False,
        realtime: Annotated[
            bool,
            typer.Option("--realtime", "-R", help="Show transcription in realtime while speaking"),
        ] = False,
        translate: Annotated[
            bool,
            typer.Option("--translate", "-T", help="Translate to English (any input language → English)"),
        ] = False,
    ) -> None:
        """Start listening for voice input (foreground).

        Uses Voice Activity Detection (VAD) to automatically detect when you speak.
        Tap the hotkey to toggle listening on/off.

        Requires --keyboard or --agents:

            voxtype listen --keyboard    # Types what you say
            voxtype listen --agents      # Starts HTTP server, agents connect via SSE

        Example with agent:

            # Terminal 1: Listen in agent mode
            voxtype listen --agents

            # Terminal 2: Start the agent (connects via SSE)
            voxtype agent claude -- claude

        For background mode, use: voxtype daemon start
        """
        from voxtype.config import load_config
        from voxtype.ui.status import LiveStatusPanel

        # Validate: require --keyboard or --agents (mutually exclusive)
        if not keyboard and not agents:
            console.print("[red]Error: Must specify --keyboard or --agents[/]")
            console.print("[dim]Examples:[/]")
            console.print("[dim]  voxtype listen --keyboard    # Types what you say[/]")
            console.print("[dim]  voxtype listen --agents      # Starts HTTP server for agents[/]")
            raise typer.Exit(1)
        if keyboard and agents:
            console.print("[red]Error: Cannot use --keyboard with --agents[/]")
            raise typer.Exit(1)

        config = load_config(config_file)

        # Apply CLI overrides first (so hw_accel is set before auto-detect)
        apply_cli_overrides(
            config,
            model=model,
            hotkey=hotkey,
            language=language,
            auto_enter=auto_enter,
            max_duration=max_duration,
            verbose=verbose,
            typing_delay=typing_delay,
            silence_ms=silence_ms,
            log_file=log_file,
            no_audio_feedback=no_audio_feedback,
            no_hw_accel=no_hw_accel,
            translate=translate,
        )

        # Quick check: verify required models are cached
        if not check_required_models(config, for_command="listen"):
            raise typer.Exit(1)

        # Auto-detect hardware acceleration (unless --no-hw-accel)
        auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

        # Auto-detect hotkey based on platform (if using default)
        if config.hotkey.key == "KEY_SCROLLLOCK" and sys.platform == "darwin":
            # macOS doesn't have ScrollLock, use Right Command instead
            config.hotkey.key = "KEY_RIGHTMETA"

        # Update config.output.mode to match CLI flag (overrides config file)
        agent_mode = agents
        config.output.mode = "agents" if agent_mode else "keyboard"

        # Lazy import to speed up CLI
        from voxtype.core.app import VoxtypeApp

        # Create JSONL logger (always enabled by default)
        # In agent mode, log path will be updated dynamically
        logger = create_logger(config, agents=["agents"] if agent_mode else None)

        voxtypeapp = VoxtypeApp(
            config,
            logger=logger,
            agent_mode=agent_mode,
            realtime=realtime,
        )

        # Create live status panel (will be started after loading)
        log_path_str = str(logger.log_path) if logger else None
        status_panel = LiveStatusPanel(config, console, agent_mode=agent_mode, log_path=log_path_str)

        # Setup signal handler for graceful shutdown (KeyboardInterrupt may not work with C extensions)
        import atexit
        import signal

        shutdown_attempted = False

        def cleanup():
            """Cleanup function registered with atexit."""
            nonlocal shutdown_attempted
            if shutdown_attempted:
                return
            shutdown_attempted = True
            try:
                voxtypeapp.stop()
                if logger:
                    logger.close()
            except Exception as e:
                console.print(f"[red]Cleanup error: {e}[/]")

        def signal_handler(signum, frame):
            nonlocal shutdown_attempted
            if shutdown_attempted:
                # Second signal - force exit
                console.print("\n[red]Force exit[/]")
                # Kill resource_tracker subprocess to prevent "leaked semaphore" warnings
                # The tracker prints warnings when resources aren't cleaned up
                import os
                import signal as sig

                try:
                    from multiprocessing.resource_tracker import _resource_tracker

                    pid: int | None = getattr(_resource_tracker, "_pid", None)
                    if pid is not None:
                        os.kill(pid, sig.SIGKILL)
                except Exception:
                    pass
                os._exit(1)

            console.print("\n[yellow]Shutting down...[/]")

            # Set a timeout for graceful shutdown
            def force_exit():
                import os
                import signal as sig
                import time

                time.sleep(3)  # Give 3 seconds for graceful shutdown
                console.print("\n[red]Shutdown timeout - forcing exit[/]")
                # Kill the resource_tracker subprocess to prevent "leaked semaphore" warnings
                try:
                    from multiprocessing.resource_tracker import _resource_tracker

                    pid: int | None = getattr(_resource_tracker, "_pid", None)
                    if pid is not None:
                        os.kill(pid, sig.SIGKILL)
                except Exception:
                    pass
                os._exit(1)

            import threading

            timer = threading.Thread(target=force_exit, daemon=True)
            timer.start()

            cleanup()
            raise SystemExit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        atexit.register(cleanup)

        try:
            voxtypeapp.run(status_panel=status_panel)
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/]")
            cleanup()
        finally:
            # atexit handles cleanup, no need to duplicate here
            pass
