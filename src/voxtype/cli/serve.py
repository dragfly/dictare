"""voxtype serve — start the engine in the foreground (Ollama-style)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer

from voxtype.cli._helpers import auto_detect_acceleration, console
from voxtype.cli.models import ensure_required_models
from voxtype.config import load_config

if TYPE_CHECKING:
    pass

def register(app: typer.Typer) -> None:
    """Register the top-level `voxtype serve` command."""

    @app.command("serve")
    def serve(
        config_file: Annotated[
            Path | None,
            typer.Option("--config", "-c", help="Path to config file"),
        ] = None,
        verbose: Annotated[
            bool,
            typer.Option("--verbose", "-v", help="Show debug logs on stdout"),
        ] = False,
    ) -> None:
        """Start the voxtype engine.

        Runs in the foreground; the service manager (launchd / systemd) handles
        backgrounding and restarts.  Use this command directly for development
        or quick testing, or let `voxtype service install` register it as a
        system service that starts at login.

        Examples:
            voxtype serve               # Start engine (service mode or dev)
            voxtype serve --verbose     # Start with debug logging on stdout
        """
        import os

        from voxtype.app import AppController
        from voxtype.utils.paths import get_pid_path

        # Check if engine already running
        pid_path = get_pid_path()
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text().strip())
                os.kill(pid, 0)  # Doesn't kill, just checks
                console.print(f"[yellow]Engine already running[/] (PID: {pid})")
                raise typer.Exit(0)
            except (ProcessLookupError, ValueError):
                pid_path.unlink(missing_ok=True)

        config = load_config(config_file)

        # Ensure required models are cached (auto-downloads if missing)
        if not ensure_required_models(config):
            raise typer.Exit(1)

        # Auto-detect hardware acceleration
        auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

        controller = AppController(config)
        _run_serve(controller, config, os, verbose=verbose)

def _run_serve(controller: Any, config: Any, os: Any, verbose: bool = False) -> None:
    """Run the engine in serve mode (foreground, logs to file + stdout).

    Called by `voxtype serve` and used internally by the service manager
    (launchd / systemd).  Always logs to the JSONL file so `voxtype logs -f`
    works.  Also writes human-readable lines to stdout so the service
    manager's journal / stdout captures useful output.
    """
    import logging
    import signal

    from voxtype import __version__
    from voxtype.logging.setup import get_default_log_path, setup_logging

    log_level = logging.DEBUG if verbose else logging.INFO

    # File logging (JSON, used by `voxtype logs -f`)
    log_path = get_default_log_path("engine")
    setup_logging(
        log_path=log_path,
        level=log_level,
        version=__version__,
        params={"mode": "serve", "pid": os.getpid()},
    )

    # Stdout logging — plain text, human-readable (like `ollama serve`)
    root_logger = logging.getLogger("voxtype")
    _stdout_handler = logging.StreamHandler()
    _stdout_handler.setLevel(log_level)
    _stdout_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-5s %(name)s  %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root_logger.addHandler(_stdout_handler)

    _logger = logging.getLogger("voxtype.serve")
    _logger.info("Starting engine (PID %s, port %s)", os.getpid(), config.server.port)
    _logger.info("Log: %s", log_path)

    # Determine initial listening state (privacy-aware: restore from saved state)
    start_listening = False
    if config.daemon.restore_listening:
        from voxtype.utils.state import load_state

        saved = load_state()
        start_listening = saved.get("listening", False)

    # NOTE: PID file is written by AppController._check_single_instance() inside
    # controller.start().  Do not write it here — writing before start() causes the
    # controller to find its own PID and refuse to start.

    from voxtype.utils.paths import get_pid_path

    try:
        try:
            controller.start(
                start_listening=start_listening,
                mode="serve",
                with_bindings=False,
            )
        except Exception as e:
            _logger.error("Engine startup failed: %s", e, exc_info=True)
            console.print(f"[red]Failed to start engine: {e}[/]")
            raise typer.Exit(1) from e

        _logger.info("Engine ready (IDLE — waiting for trigger)")

        # Signal handlers
        def signal_handler(signum: int, frame: Any) -> None:
            _logger.info("Shutting down (signal %s)", signum)
            controller.request_shutdown()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # SIGUSR1 = toggle listening (sent by Swift launcher on hotkey tap)
        if hasattr(signal, "SIGUSR1"):

            def _toggle_handler(signum: int, frame: Any) -> None:
                _logger.info("SIGUSR1 received — toggling listening")
                controller.toggle_listening()

            signal.signal(signal.SIGUSR1, _toggle_handler)

        # Run main loop (blocks until shutdown)
        try:
            controller.run()
        except KeyboardInterrupt:
            pass
    finally:
        get_pid_path().unlink(missing_ok=True)
        controller.stop()
        _logger.info("Engine stopped")
        _kill_resource_tracker(os)
        os._exit(0)

def _kill_resource_tracker(os: Any) -> None:
    """Kill resource_tracker subprocess to prevent leaked semaphore warnings."""
    import signal as sig

    try:
        from multiprocessing.resource_tracker import _resource_tracker  # type: ignore[attr-defined]

        pid: int | None = getattr(_resource_tracker, "_pid", None)
        if pid is not None:
            os.kill(pid, sig.SIGKILL)
    except Exception:
        pass
