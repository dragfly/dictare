"""Engine management commands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from voxtype.cli._helpers import auto_detect_acceleration, console
from voxtype.cli.models import check_required_models
from voxtype.config import load_config

app = typer.Typer(help="Manage the engine.", no_args_is_help=True)

@app.command("start")
def engine_start(
    daemon: Annotated[
        bool,
        typer.Option("--daemon", "-d", help="Run as background daemon"),
    ] = False,
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
    # Output mode
    keyboard: Annotated[
        bool,
        typer.Option("--keyboard", "-K", help="Keyboard mode - types what you say"),
    ] = False,
    agents: Annotated[
        bool,
        typer.Option("--agents", "-A", help="Agent mode - starts HTTP server for SSE agents"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show debug logs (disables loading panel)"),
    ] = False,
) -> None:
    """Start the voxtype engine.

    Foreground mode (default):
        voxtype engine start --keyboard    # Types what you say, listening immediately
        voxtype engine start --agents      # Agent mode, listening immediately

    Daemon mode (background):
        voxtype engine start -d --agents   # Background, models loaded, waiting for trigger

    In daemon mode, the engine preloads models but stays IDLE until activated
    via tray click, hotkey, or API call.
    """
    import os

    from voxtype.app import AppController
    from voxtype.engine.engine import get_pid_path

    # Validate: require --keyboard or --agents
    if not keyboard and not agents:
        console.print("[red]Error: Must specify --keyboard or --agents[/]")
        console.print("[dim]Examples:[/]")
        console.print("[dim]  voxtype engine start --keyboard    # Types what you say[/]")
        console.print("[dim]  voxtype engine start --agents      # Starts HTTP server for agents[/]")
        raise typer.Exit(1)
    if keyboard and agents:
        console.print("[red]Error: Cannot use --keyboard with --agents[/]")
        raise typer.Exit(1)

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
    if verbose:
        config.verbose = True

    # Apply CLI overrides
    if model:
        config.stt.model = model
    if language:
        config.stt.language = language
    config.output.mode = "agents" if agents else "keyboard"

    # Quick check: verify required models are cached
    if not check_required_models(config, for_command="engine"):
        raise typer.Exit(1)

    # Auto-detect hardware acceleration
    auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

    # Auto-detect hotkey based on platform
    if config.hotkey.key == "KEY_SCROLLLOCK" and sys.platform == "darwin":
        config.hotkey.key = "KEY_RIGHTMETA"

    # Create AppController
    controller = AppController(config)

    if daemon:
        _run_daemon(controller, config, os)
    else:
        _run_foreground(controller, config, verbose, os)

def _run_daemon(controller, config, os) -> None:
    """Run engine in daemon mode (headless)."""
    import signal

    console.print(f"[dim]Starting engine in daemon mode (PID: {os.getpid()})...[/]")
    console.print(f"[dim]HTTP: http://{config.server.host}:{config.server.port}[/]")

    try:
        controller.start(
            start_listening=False,  # Privacy-aware: don't listen until triggered
            mode="daemon",
            with_bindings=False,  # No keyboard bindings in daemon mode
        )
    except Exception as e:
        console.print(f"[red]Failed to start engine: {e}[/]")
        raise typer.Exit(1)

    console.print("[green]Engine ready[/] (IDLE - waiting for trigger)")

    # Setup signal handlers
    def signal_handler(signum: int, frame: Any) -> None:
        console.print("\n[yellow]Shutting down...[/]")
        controller.request_shutdown()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Run main loop (blocks until shutdown)
    try:
        controller.run()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
        console.print("[dim]Engine stopped[/]")
        _kill_resource_tracker(os)
        os._exit(0)

def _run_foreground(controller, config, verbose: bool, os) -> None:
    """Run engine in foreground with UI."""
    import threading

    base_url = f"http://{config.server.host}:{config.server.port}"
    init_error: Exception | None = None
    init_done = threading.Event()

    def do_init() -> None:
        """Initialize AppController."""
        nonlocal init_error
        try:
            controller.start(
                start_listening=True,
                mode="foreground",
                with_bindings=True,
            )
        except Exception as e:
            init_error = e
        finally:
            init_done.set()

    def run_controller() -> None:
        """Run controller main loop after init completes."""
        init_done.wait()
        if init_error:
            return
        controller.run()

    # Start initialization
    init_thread = threading.Thread(target=do_init, daemon=True)
    init_thread.start()

    # Start main loop
    controller_thread = threading.Thread(target=run_controller, daemon=True)
    controller_thread.start()

    shutdown_attempted = False

    if verbose:
        _run_verbose_mode(
            controller, controller_thread, init_done, init_error,
            base_url, config, os, shutdown_attempted,
        )
    else:
        _run_panel_mode(
            controller, controller_thread, init_done, init_error,
            base_url, os, shutdown_attempted,
        )

def _run_verbose_mode(
    controller, controller_thread, init_done, init_error,
    base_url, config, os, shutdown_attempted,
) -> None:
    """Verbose mode: plain text logging, no Live panel."""
    import json
    import logging as _logging
    import signal
    import threading
    import time as _time
    import urllib.request

    # Enable debug logging to stderr so user sees engine internals
    _logging.basicConfig(
        level=_logging.DEBUG,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    def _color(status: str) -> str:
        return {"done": "green", "loading": "cyan", "error": "red"}.get(status, "dim")

    console.print(f"[dim]Engine starting (verbose mode) — {base_url}[/]")
    console.print(f"[dim]Device: {config.stt.device}, Model: {config.stt.model}, "
                  f"Compute: {config.stt.compute_type}[/]")

    def signal_handler(signum: int, frame: Any) -> None:
        nonlocal shutdown_attempted
        if shutdown_attempted:
            _kill_resource_tracker(os)
            os._exit(1)
        shutdown_attempted = True
        console.print("\n[yellow]Shutting down...[/]")

        def _force_exit() -> None:
            _time.sleep(3)
            _kill_resource_tracker(os)
            os._exit(1)

        threading.Thread(target=_force_exit, daemon=True).start()
        controller.request_shutdown()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Poll /status and print changes
    last_status: dict = {}
    try:
        while not init_done.is_set() or (not init_error and controller.is_running):
            try:
                req = urllib.request.Request(f"{base_url}/status")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    status = json.loads(resp.read())
            except Exception:
                status = {}

            # Print loading progress changes
            platform = status.get("platform", {})
            loading = platform.get("loading", {})
            models = loading.get("models", [])
            for m in models:
                name = m.get("name", "?")
                st = m.get("status", "?")
                elapsed = m.get("elapsed", 0)
                key = f"{name}_status"
                if last_status.get(key) != st:
                    console.print(f"  [{_color(st)}]{name}: {st}[/] ({elapsed:.1f}s)")
                    last_status[key] = st

            if not loading.get("active", True) and "ready" not in last_status:
                console.print("[green]Engine ready[/]")
                last_status["ready"] = True

            if init_error:
                console.print(f"[red]Init error: {init_error}[/]")
                break

            _time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    # Wait for shutdown or report error
    if init_error:
        console.print(f"[red]Init failed: {init_error}[/]")
        import traceback

        traceback.print_exception(type(init_error), init_error, init_error.__traceback__)
    else:
        try:
            controller_thread.join()
        except KeyboardInterrupt:
            pass
    controller.stop()
    _kill_resource_tracker(os)
    os._exit(1 if init_error else 0)

def _run_panel_mode(
    controller, controller_thread, init_done, init_error,
    base_url, os, shutdown_attempted,
) -> None:
    """Normal mode: StatusPanel with Rich Live."""
    import signal
    import threading

    from voxtype.ui.panel import StatusPanel

    # Run StatusPanel in main thread (polls /status, shows UI)
    panel = StatusPanel(console, base_url)

    def signal_handler(signum: int, frame: Any) -> None:
        nonlocal shutdown_attempted
        if shutdown_attempted:
            _kill_resource_tracker(os)
            os._exit(1)

        shutdown_attempted = True
        panel.stop()

        def force_exit() -> None:
            import time

            time.sleep(3)
            _kill_resource_tracker(os)
            os._exit(1)

        threading.Thread(target=force_exit, daemon=True).start()
        controller.request_shutdown()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        panel.run()
    except KeyboardInterrupt:
        pass
    finally:
        panel.stop()
        controller.stop()
        _kill_resource_tracker(os)
        os._exit(0)

@app.command("stop")
def engine_stop() -> None:
    """Stop the running engine."""
    from voxtype.engine import get_pid_path

    pid_path = get_pid_path()
    if not pid_path.exists():
        console.print("[yellow]Engine is not running[/]")
        raise typer.Exit(0)

    try:
        pid = int(pid_path.read_text().strip())
    except ValueError:
        console.print("[red]Invalid PID file[/]")
        pid_path.unlink(missing_ok=True)
        raise typer.Exit(1)

    import os
    import signal

    try:
        os.kill(pid, 0)  # Check if running
    except ProcessLookupError:
        console.print("[yellow]Engine is not running (stale PID file)[/]")
        pid_path.unlink(missing_ok=True)
        raise typer.Exit(0)

    console.print(f"[dim]Stopping engine (PID: {pid})...[/]")

    try:
        os.kill(pid, signal.SIGTERM)
        # Wait for process to exit
        import time

        for _ in range(30):  # 3 seconds timeout
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                console.print("[green]Engine stopped[/]")
                return
        # Still running, force kill
        console.print("[yellow]Engine not responding, forcing...[/]")
        os.kill(pid, signal.SIGKILL)
        console.print("[green]Engine stopped (forced)[/]")
    except Exception as e:
        console.print(f"[red]Failed to stop engine: {e}[/]")
        raise typer.Exit(1)

@app.command("status")
def engine_status(
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """Show engine status."""
    import json

    from voxtype.engine import get_pid_path

    pid_path = get_pid_path()
    if not pid_path.exists():
        if json_output:
            console.print(json.dumps({"running": False}))
        else:
            console.print("[yellow]Engine is not running[/]")
        raise typer.Exit(0)

    try:
        pid = int(pid_path.read_text().strip())
        import os

        os.kill(pid, 0)  # Check if running
    except (ValueError, ProcessLookupError):
        if json_output:
            console.print(json.dumps({"running": False, "stale_pid": True}))
        else:
            console.print("[yellow]Engine is not running (stale PID file)[/]")
        raise typer.Exit(0)

    # Engine is running, try to get status via HTTP
    import urllib.error
    import urllib.request

    try:
        config = load_config()
        url = f"http://{config.server.host}:{config.server.port}/status"
        with urllib.request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode())

        if json_output:
            data["running"] = True
            data["pid"] = pid
            console.print(json.dumps(data, indent=2))
        else:
            console.print(f"[green]Engine is running[/] (PID: {pid})")
            engine_state = data.get("engine", {})
            stt_state = data.get("stt", {})
            output_state = data.get("output", {})

            console.print(f"  Mode: {engine_state.get('mode', 'unknown')}")
            console.print(f"  Version: {engine_state.get('version', 'unknown')}")

            uptime = engine_state.get("uptime_seconds", 0)
            if uptime < 60:
                uptime_str = f"{uptime:.0f}s"
            elif uptime < 3600:
                uptime_str = f"{uptime / 60:.1f}m"
            else:
                uptime_str = f"{uptime / 3600:.1f}h"
            console.print(f"  Uptime: {uptime_str}")

            console.print(f"  STT state: {stt_state.get('state', 'unknown')}")
            console.print(f"  STT model: {stt_state.get('model_name', 'not loaded')}")
            console.print(f"  Output mode: {output_state.get('mode', 'unknown')}")

            agents = output_state.get("available_agents", [])
            if agents:
                current = output_state.get("current_agent", "")
                console.print(f"  Agents: {len(agents)} available")
                for agent in agents:
                    marker = " *" if agent == current else ""
                    console.print(f"    - {agent}{marker}")
    except urllib.error.URLError:
        if json_output:
            console.print(json.dumps({"running": True, "pid": pid, "http_unavailable": True}))
        else:
            console.print(f"[green]Engine is running[/] (PID: {pid})")
            console.print("[dim]  HTTP endpoint not available[/]")
    except Exception as e:
        if json_output:
            console.print(json.dumps({"running": True, "pid": pid, "error": str(e)}))
        else:
            console.print(f"[green]Engine is running[/] (PID: {pid})")
            console.print(f"[dim]  Could not get status: {e}[/]")

def _kill_resource_tracker(os) -> None:
    """Kill resource_tracker subprocess to prevent leaked semaphore warnings."""
    import signal as sig

    try:
        from multiprocessing.resource_tracker import _resource_tracker

        pid: int | None = getattr(_resource_tracker, "_pid", None)
        if pid is not None:
            os.kill(pid, sig.SIGKILL)
    except Exception:
        pass
