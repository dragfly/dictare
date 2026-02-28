"""dictare serve — start the engine in the foreground (Ollama-style)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer

from dictare.cli._helpers import auto_detect_acceleration, console
from dictare.cli.models import ensure_required_models
from dictare.config import load_config

if TYPE_CHECKING:
    pass


def register(app: typer.Typer) -> None:
    """Register the top-level `dictare serve` command."""

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
        """Start the dictare engine.

        Runs in the foreground; the service manager (launchd / systemd) handles
        backgrounding and restarts.  Use this command directly for development
        or quick testing, or let `dictare service install` register it as a
        system service that starts at login.

        Examples:
            dictare serve               # Start engine (service mode or dev)
            dictare serve --verbose     # Start with debug logging on stdout
        """
        import os

        from dictare.app import AppController
        from dictare.utils.paths import get_pid_path

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

        # Download missing models in background — engine starts immediately.
        # STT/TTS gracefully degrade until their model is ready.
        import threading

        def _bg_download() -> None:
            try:
                ensure_required_models(config)
            except Exception:
                import logging

                logging.getLogger("dictare.serve").warning(
                    "Background model download failed — "
                    "run 'dictare models pull' manually",
                    exc_info=True,
                )

        threading.Thread(target=_bg_download, daemon=True).start()

        # Auto-detect hardware acceleration
        auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

        controller = AppController(config)
        _run_serve(controller, config, os, verbose=verbose)


def _run_serve(controller: Any, config: Any, os: Any, verbose: bool = False) -> None:
    """Run the engine in serve mode (foreground, logs to file + stdout).

    Called by `dictare serve` and used internally by the service manager
    (launchd / systemd).  Always logs to the JSONL file so `dictare logs -f`
    works.  Also writes human-readable lines to stdout so the service
    manager's journal / stdout captures useful output.
    """
    import logging
    import signal

    from dictare import __version__
    from dictare.logging.setup import get_default_log_path, setup_logging

    log_level = logging.DEBUG if verbose else logging.INFO

    # File logging (JSON, used by `dictare logs -f`)
    log_path = get_default_log_path("engine")
    setup_logging(
        log_path=log_path,
        level=log_level,
        version=__version__,
        params={"mode": "serve", "pid": os.getpid()},
        source="engine",
    )

    # Stdout logging — plain text, human-readable (like `ollama serve`)
    root_logger = logging.getLogger("dictare")
    _stdout_handler = logging.StreamHandler()
    _stdout_handler.setLevel(log_level)
    _stdout_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-5s %(name)s  %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root_logger.addHandler(_stdout_handler)

    _logger = logging.getLogger("dictare.serve")

    from dictare import __version__

    _logger.info("dictare %s starting (PID %s, port %s)", __version__, os.getpid(), config.server.port)
    _logger.info("Log: %s", log_path)

    # Listening state is restored by engine._restore_state() — not here.
    start_listening = False

    # NOTE: PID file is written by AppController._check_single_instance() inside
    # controller.start().  Do not write it here — writing before start() causes the
    # controller to find its own PID and refuse to start.

    from dictare.utils.paths import get_pid_path

    hotkey_ipc = None

    try:
        # Install signal handlers BEFORE controller.start() — model loading
        # takes ~20s and an unhandled SIGUSR1 during that window kills the process.
        def signal_handler(signum: int, frame: Any) -> None:
            _logger.info("Shutting down dictare %s (signal %s)", __version__, signum)
            controller.request_shutdown()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        if hasattr(signal, "SIGUSR1"):

            def _tap_handler(signum: int, frame: Any) -> None:
                _logger.info("SIGUSR1 received — hotkey tap")
                controller.on_hotkey_tap()

            signal.signal(signal.SIGUSR1, _tap_handler)

        hotkey_transport = os.environ.get("DICTARE_HOTKEY_TRANSPORT", "auto").strip().lower()
        if hotkey_transport in ("auto", "ipc"):
            try:
                from dictare.hotkey.ipc import HotkeyIPCServer

                hotkey_ipc = HotkeyIPCServer(on_tap=controller.on_hotkey_tap)
                hotkey_ipc.start()
                _logger.info("Hotkey transport active: ipc+signal-fallback")
            except Exception:
                _logger.warning("Failed to start hotkey IPC server, using signal-only", exc_info=True)
        else:
            _logger.info("Hotkey transport active: signal-only")

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

        _logger.info("Engine ready")

        # Run main loop (blocks until shutdown)
        try:
            controller.run()
        except KeyboardInterrupt:
            pass
    finally:
        if hotkey_ipc is not None:
            hotkey_ipc.stop()
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
