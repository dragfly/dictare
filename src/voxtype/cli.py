"""CLI interface for voxtype."""

from __future__ import annotations

import os

# Disable HuggingFace progress bars globally (must be before any HF imports)
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from voxtype import __version__
from voxtype.config import (
    ConfigError,
    create_default_config,
    get_config_path,
    get_config_value,
    list_config_keys,
    load_config,
    set_config_value,
)
from voxtype.ui.status import LiveStatusPanel

app = typer.Typer(
    name="voxtype",
    help="Voice-to-text for your terminal",
    add_completion=True,  # Required for shell completion to work at runtime
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,  # Disable rich formatting for errors
)

# Completion subcommand
completion_app = typer.Typer(help="Manage shell completion", no_args_is_help=True)
app.add_typer(completion_app, name="completion")

# Daemon subcommand
daemon_app = typer.Typer(help="Manage the voxtype daemon", no_args_is_help=True)
app.add_typer(daemon_app, name="daemon")

# Models subcommand
models_app = typer.Typer(help="Manage TTS/STT models", no_args_is_help=True)
app.add_typer(models_app, name="models")

# Dependencies subcommand
deps_app = typer.Typer(help="Manage system dependencies", no_args_is_help=True)
app.add_typer(deps_app, name="dependencies")

# Tray subcommand
tray_app = typer.Typer(help="System tray integration", no_args_is_help=True)
app.add_typer(tray_app, name="tray")

# Engine subcommand (new architecture)
engine_app = typer.Typer(help="Engine management (new architecture)", no_args_is_help=True)
app.add_typer(engine_app, name="engine")


def _register_plugins() -> None:
    """Discover and register plugin commands."""
    import logging

    from voxtype.plugins import discover_plugins
    from voxtype.services import ServiceRegistry

    # Create service registry for plugins
    registry = ServiceRegistry()

    for plugin_cls in discover_plugins():
        try:
            plugin = plugin_cls()
            plugin.on_load(registry)

            if commands := plugin.get_commands():
                app.add_typer(commands, name=plugin.name, help=plugin.description)
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Failed to register plugin '{plugin_cls.__name__}': {e}"
            )


# Register plugins at import time (lazy loaded)
_plugins_registered = False


def _ensure_plugins_registered() -> None:
    """Ensure plugins are registered (called once)."""
    global _plugins_registered
    if not _plugins_registered:
        _register_plugins()
        _plugins_registered = True


console = Console(
    force_terminal=None,  # Auto-detect
    force_interactive=None,  # Auto-detect
    legacy_windows=False,  # Use modern terminal codes
    safe_box=True,  # Use safe box drawing chars for compatibility
)


# Shell completion paths by shell type
COMPLETION_PATHS = {
    "bash": "~/.bash_completion.d/voxtype.bash",
    "zsh": "~/.zfunc/_voxtype",
    "fish": "~/.config/fish/completions/voxtype.fish",
}


def _get_shell() -> str:
    """Detect current shell."""
    import os
    shell_path = os.environ.get("SHELL", "")
    if "zsh" in shell_path:
        return "zsh"
    elif "fish" in shell_path:
        return "fish"
    return "bash"


def _get_completion_script(shell: str) -> str:
    """Generate completion script for shell."""
    import typer.completion

    # Map shell names to typer's expected format
    shell_map = {
        "bash": "bash",
        "zsh": "zsh",
        "fish": "fish",
    }

    if shell not in shell_map:
        return ""

    # Use typer's built-in completion script generation
    return typer.completion.get_completion_script(
        prog_name="voxtype",
        complete_var="_VOXTYPE_COMPLETE",
        shell=shell_map[shell],
    )


@completion_app.command("install")
def completion_install(
    shell: Annotated[str | None, typer.Argument(help="Shell type (bash/zsh/fish)")] = None,
) -> None:
    """Install shell completion."""
    shell = shell or _get_shell()

    if shell not in COMPLETION_PATHS:
        console.print(f"[red]Unsupported shell: {shell}[/]")
        console.print("Supported: bash, zsh, fish")
        raise typer.Exit(1)

    script = _get_completion_script(shell)
    if not script or "not supported" in script.lower():
        console.print(f"[red]Could not generate completion script for {shell}[/]")
        raise typer.Exit(1)

    # Expand path and create parent dirs
    path = Path(COMPLETION_PATHS[shell]).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write completion script
    path.write_text(script)
    console.print(f"[green]Installed completion to {path}[/]")

    # Shell-specific instructions
    if shell == "zsh":
        console.print("\nAdd to ~/.zshrc if not already present:")
        console.print("  [dim]fpath=(~/.zfunc $fpath)[/]")
        console.print("  [dim]autoload -Uz compinit && compinit[/]")
    elif shell == "bash":
        console.print("\nAdd to ~/.bashrc if not already present:")
        console.print(f"  [dim]source {path}[/]")
    elif shell == "fish":
        console.print("\n[green]Fish will load it automatically.[/]")


@completion_app.command("show")
def completion_show(
    shell: Annotated[str | None, typer.Argument(help="Shell type (bash/zsh/fish)")] = None,
) -> None:
    """Show completion script (for manual installation)."""
    shell = shell or _get_shell()
    script = _get_completion_script(shell)

    if not script or "not supported" in script.lower():
        console.print(f"[red]Could not generate completion script for {shell}[/]")
        raise typer.Exit(1)

    print(script)


@completion_app.command("remove")
def completion_remove(
    shell: Annotated[str | None, typer.Argument(help="Shell type (bash/zsh/fish)")] = None,
) -> None:
    """Remove installed shell completion."""
    shell = shell or _get_shell()

    if shell not in COMPLETION_PATHS:
        console.print(f"[red]Unsupported shell: {shell}[/]")
        raise typer.Exit(1)

    path = Path(COMPLETION_PATHS[shell]).expanduser()

    if path.exists():
        path.unlink()
        console.print(f"[green]Removed {path}[/]")
    else:
        console.print(f"[yellow]No completion file found at {path}[/]")


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"voxtype version {__version__}")
        raise typer.Exit()


def _auto_detect_acceleration(config, cpu_only: bool = False) -> None:
    """Auto-detect hardware acceleration (MLX on macOS, CUDA on Linux)."""
    from voxtype.utils.hardware import auto_detect_acceleration
    auto_detect_acceleration(config, cpu_only=cpu_only, console=console)


def _apply_cli_overrides(
    config,
    *,
    model: str | None,
    hotkey: str | None,
    language: str | None,
    auto_enter: bool,
    max_duration: int | None,
    verbose: bool | None,
    typing_delay: int | None,
    silence_ms: int | None,
    log_file: str | None,
    no_audio_feedback: bool,
    no_hw_accel: bool,
    translate: bool = False,
) -> None:
    """Apply CLI options to config.

    Boolean flags use negative form (--no-X) for features that are ON by default.
    """
    if model:
        config.stt.model = model
    if hotkey:
        config.hotkey.key = hotkey
    if language:
        config.stt.language = language
    if auto_enter:
        config.output.auto_enter = True
    if max_duration:
        config.audio.max_duration = max_duration
    if verbose is not None:
        config.verbose = verbose
    if typing_delay is not None:
        config.output.typing_delay_ms = typing_delay
    if silence_ms is not None:
        config.audio.silence_ms = silence_ms
    if log_file:
        config.logging.log_file = log_file
    if no_audio_feedback:
        config.audio.audio_feedback = False
    if no_hw_accel:
        config.stt.hw_accel = False
    if translate:
        config.stt.translate = True


def _create_logger(config, agents: list[str] | None = None):
    """Create JSONL logger for session.

    Logging is always enabled by default to ~/.local/share/voxtype/logs/.
    - INFO level (default): metadata only (chars, duration) - no text content
    - DEBUG level (--verbose): includes actual text content

    Args:
        config: Application configuration.
        agents: Optional list of agent IDs (affects log file name).

    Returns:
        JSONLLogger instance.
    """
    from voxtype.logging.jsonl import JSONLLogger, LogLevel, get_default_log_path

    # Determine log level from verbose flag
    level = LogLevel.DEBUG if config.verbose else LogLevel.INFO

    # Determine log file path
    if config.logging.log_file:
        # User specified a custom log file
        log_path = Path(config.logging.log_file)
    else:
        # Use default path based on mode
        if agents:
            # Multi-agent: use first agent name
            log_path = get_default_log_path(f"agent.{agents[0]}")
        else:
            log_path = get_default_log_path("listen")

    log_params = {
        "input_mode": "vad",  # PTT mode removed in v2.2.0
        "log_level": level.name,
        "silence_ms": config.audio.silence_ms,
        "stt_model": config.stt.model,
        "stt_language": config.stt.language,
        "output_mode": config.output.mode,
    }
    if agents:
        log_params["agents"] = agents

    return JSONLLogger(log_path, __version__, level=level, params=log_params)


@app.callback()
def main_callback(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """voxtype: Voice-to-text for your terminal."""
    pass


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
    _apply_cli_overrides(
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
    if not _check_required_models(config, for_command="listen"):
        raise typer.Exit(1)

    # Auto-detect hardware acceleration (unless --no-hw-accel)
    _auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

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
    logger = _create_logger(config, agents=["agents"] if agent_mode else None)

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


def _check_dependencies_internal() -> tuple[list, bool, list, list]:
    """Check dependencies and return results.

    Returns:
        Tuple of (results, all_ok, missing_with_hints, optional_with_hints)
    """
    from voxtype.utils.platform import check_dependencies

    results = check_dependencies()

    all_ok = True
    missing_with_hints = []
    optional_with_hints = []

    for result in results:
        if result.available:
            pass  # OK
        elif result.required:
            all_ok = False
            if result.install_hint:
                missing_with_hints.append(result)
        else:
            if result.install_hint:
                optional_with_hints.append(result)

    return results, all_ok, missing_with_hints, optional_with_hints


def _display_dependencies(results, all_ok: bool, missing_with_hints: list, optional_with_hints: list) -> None:
    """Display dependency check results."""
    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    for result in results:
        if result.available:
            status = "[green]OK[/]"
        elif result.required:
            status = "[red]MISSING[/]"
        else:
            status = "[yellow]OPTIONAL[/]"

        table.add_row(result.name, status, result.message)

    console.print(table)
    console.print()

    if all_ok:
        console.print("[green]All required dependencies are available![/]")
        # Show GPU acceleration hint if applicable
        gpu_hints = [r for r in optional_with_hints if r.name in ("NVIDIA GPU", "Apple Silicon")]
        if gpu_hints:
            console.print("\n[bold]To enable hardware acceleration:[/]")
            for result in gpu_hints:
                hint = result.install_hint.replace("[", r"\[")  # type: ignore
                console.print(f"  [cyan]{hint}[/]")
    else:
        console.print("[red]Some required dependencies are missing.[/]")
        if missing_with_hints:
            console.print("\n[bold]To fix, run:[/]")
            # Deduplicate hints
            seen_hints: set[str] = set()
            for result in missing_with_hints:
                if result.install_hint and result.install_hint not in seen_hints:
                    seen_hints.add(result.install_hint)
                    hint = result.install_hint.replace("[", r"\[")
                    console.print(f"  [cyan]{hint}[/]")
        console.print("\n[dim]Or run: voxtype dependencies resolve[/]")

    # Check for text injection method (Linux only)
    if sys.platform == "linux":
        has_ydotool = any(r.available for r in results if r.name == "ydotool")
        if not has_ydotool:
            console.print(
                "\n[red]Warning:[/] ydotool not available. "
                "Install ydotool and start ydotoold daemon."
            )


@deps_app.command("check")
def deps_check() -> None:
    """Check system dependencies.

    Shows status of all required and optional dependencies.
    """
    console.print("[dim]Checking dependencies...[/]")

    results, all_ok, missing_with_hints, optional_with_hints = _check_dependencies_internal()
    _display_dependencies(results, all_ok, missing_with_hints, optional_with_hints)

    if not all_ok:
        raise typer.Exit(1)


@deps_app.command("resolve")
def deps_resolve(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be installed without installing"),
    ] = False,
) -> None:
    """Automatically resolve missing dependencies.

    Attempts to install missing dependencies using system package managers
    (brew on macOS, apt on Linux) and pip.

    Examples:
        voxtype dependencies resolve           # Install missing deps
        voxtype dependencies resolve --dry-run # Show what would be installed
    """
    import subprocess

    console.print("[dim]Checking dependencies...[/]")

    results, all_ok, missing_with_hints, _ = _check_dependencies_internal()

    if all_ok:
        console.print("[green]All dependencies are already satisfied![/]")
        raise typer.Exit(0)

    # Collect install commands
    commands: list[str] = []
    seen_hints: set[str] = set()

    for result in missing_with_hints:
        if result.install_hint and result.install_hint not in seen_hints:
            seen_hints.add(result.install_hint)
            commands.append(result.install_hint)

    if not commands:
        console.print("[yellow]No automatic install commands available for missing dependencies.[/]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Will run {len(commands)} command(s):[/]")
    for cmd in commands:
        console.print(f"  [cyan]{cmd}[/]")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made[/]")
        raise typer.Exit(0)

    console.print()

    # Execute commands
    failed = 0
    for cmd in commands:
        console.print(f"[bold]Running:[/] {cmd}")
        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            console.print(f"[red]Command failed with exit code {result.returncode}[/]")
            failed += 1
        else:
            console.print("[green]OK[/]")
        console.print()

    # Re-check
    console.print("[dim]Re-checking dependencies...[/]")
    results, all_ok, _, _ = _check_dependencies_internal()

    if all_ok:
        console.print("[green]All dependencies are now satisfied![/]")
    else:
        console.print("[yellow]Some dependencies still missing (run 'voxtype dependencies check' for details)[/]")
        raise typer.Exit(1)


@app.command()
def init() -> None:
    """Create default configuration file."""
    config_path = get_config_path()

    if config_path.exists():
        if not typer.confirm(f"Config file already exists at {config_path}. Overwrite?"):
            raise typer.Abort()

    created_path = create_default_config()
    console.print(f"[green]Created config file:[/] {created_path}")
    console.print("\nEdit this file to customize settings:")
    console.print(f"  [cyan]{created_path}[/]")


# Config subcommands
config_app = typer.Typer(help="Manage configuration", no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("list")
def config_list() -> None:
    """List all configuration options with current values."""
    _show_config_list()


def _show_config_list() -> None:
    """Show all config keys in a table."""
    config_path = get_config_path()
    cfg = load_config()

    table = Table(
        show_header=True,
        header_style="bold",
        title="Configuration",
        title_style="bold green",
        expand=False,
    )
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="yellow")
    table.add_column("Env Override", style="dim")

    for key, type_name, default, description, env_var in list_config_keys():
        try:
            current = get_config_value(key, cfg)
            # Format value for display
            if current is None:
                value_str = "[dim]null[/]"
            elif isinstance(current, bool):
                value_str = "[green]true[/]" if current else "[red]false[/]"
            else:
                value_str = str(current)
        except KeyError:
            value_str = "[red]error[/]"

        table.add_row(key, value_str, env_var)

    console.print(table)

    if config_path.exists():
        console.print(f"[dim]Config file: {config_path}[/]")
    else:
        console.print(f"[dim]Config file: {config_path} (not created, using defaults)[/]")
        console.print("[dim]Run 'voxtype init' to create config file[/]")


@config_app.command("get")
def config_get(
    ctx: typer.Context,
    key: Annotated[str | None, typer.Argument(help="Config key (e.g., stt.model)")] = None,
) -> None:
    """Get a configuration value."""
    if key is None:
        import click
        click.echo(ctx.get_help())
        raise typer.Exit(0)

    try:
        value = get_config_value(key)
        console.print(value)
    except KeyError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)


@config_app.command("set")
def config_set(
    ctx: typer.Context,
    key: Annotated[str | None, typer.Argument(help="Config key (e.g., stt.model)")] = None,
    value: Annotated[str | None, typer.Argument(help="Value to set")] = None,
) -> None:
    """Set a configuration value."""
    if key is None or value is None:
        import click
        click.echo(ctx.get_help())
        raise typer.Exit(0)

    try:
        set_config_value(key, value)
        console.print(f"[green]✓[/] Set [cyan]{key}[/] = [yellow]{value}[/]")
    except KeyError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Invalid value:[/] {e}")
        raise typer.Exit(1)


@config_app.command("path")
def config_path_cmd() -> None:
    """Show config file path."""
    console.print(get_config_path())


@config_app.command("shortcuts")
def config_shortcuts() -> None:
    """Configure keyboard shortcuts interactively.

    Opens an interactive UI to set global keyboard shortcuts for voxtype commands.
    Shortcuts work system-wide while voxtype is running.
    """
    from voxtype.ui import configure_shortcuts

    configure_shortcuts()


# Daemon commands
@daemon_app.command("start")
def daemon_start(
    foreground: Annotated[
        bool,
        typer.Option("--foreground", "-f", help="Run in foreground (for systemd/launchd)"),
    ] = False,
) -> None:
    """Start the voxtype daemon.

    The daemon keeps TTS/STT models loaded in memory for fast responses.

    Examples:
        voxtype daemon start              # Background
        voxtype daemon start --foreground # Foreground (for systemd/launchd)
    """
    from voxtype.daemon import get_daemon_status, start_daemon

    status = get_daemon_status()
    if status.running:
        console.print(f"[yellow]Daemon already running[/] (PID: {status.pid})")
        raise typer.Exit(0)

    # Quick check: verify required models are cached
    if not _check_required_models(for_command="daemon"):
        raise typer.Exit(1)

    if foreground:
        console.print("[dim]Starting daemon in foreground...[/]")
        result = start_daemon(foreground=True)
    else:
        console.print("[dim]Starting daemon...[/]")
        result = start_daemon(foreground=False)

        if result == 0:
            # Verify it started
            import time

            time.sleep(0.5)
            status = get_daemon_status()
            if status.running:
                console.print(f"[green]Daemon started[/] (PID: {status.pid})")
            else:
                console.print("[red]Daemon failed to start[/]")
                console.print("[dim]Check logs: ~/.local/share/voxtype/daemon.log[/]")
                raise typer.Exit(1)
        else:
            console.print("[red]Failed to start daemon[/]")
            raise typer.Exit(1)


@daemon_app.command("stop")
def daemon_stop() -> None:
    """Stop the voxtype daemon."""
    from voxtype.daemon import get_daemon_status, stop_daemon

    status = get_daemon_status()
    if not status.running:
        console.print("[yellow]Daemon is not running[/]")
        raise typer.Exit(0)

    console.print(f"[dim]Stopping daemon (PID: {status.pid})...[/]")
    result = stop_daemon()

    if result == 0:
        console.print("[green]Daemon stopped[/]")
    else:
        console.print("[red]Failed to stop daemon[/]")
        raise typer.Exit(1)


@daemon_app.command("status")
def daemon_status_cmd() -> None:
    """Show daemon status."""
    from voxtype.daemon import get_daemon_status
    from voxtype.daemon.client import DaemonClient, is_daemon_running

    status = get_daemon_status()

    if not status.running:
        console.print("[yellow]Daemon is not running[/]")
        if status.socket_exists:
            console.print("[dim]Stale socket file exists (will be cleaned on next start)[/]")
        raise typer.Exit(0)

    console.print(f"[green]Daemon is running[/] (PID: {status.pid})")

    # Try to get detailed status from daemon
    if is_daemon_running():
        from voxtype.daemon.protocol import StatusResponse

        try:
            client = DaemonClient()
            response = client.get_status()

            if isinstance(response, StatusResponse):
                uptime = response.uptime_seconds
                if uptime < 60:
                    uptime_str = f"{uptime:.0f}s"
                elif uptime < 3600:
                    uptime_str = f"{uptime / 60:.1f}m"
                else:
                    uptime_str = f"{uptime / 3600:.1f}h"
                console.print(f"  State: {response.state}")
                console.print(f"  Uptime: {uptime_str}")
                console.print(f"  Requests served: {response.requests_served}")
                console.print(f"  Output mode: {response.output_mode}")
                # Always show agents info for debugging
                agents_list = response.available_agents or []
                console.print(f"  Agents: {len(agents_list)} available")
                if agents_list:
                    for agent in agents_list:
                        marker = " *" if agent == response.current_agent else ""
                        console.print(f"    - {agent}{marker}")
                console.print(f"  STT loaded: {'yes' if response.stt_loaded else 'no'}")
                console.print(f"  TTS loaded: {'yes' if response.tts_loaded else 'no'}")
                if response.tts_engine:
                    console.print(f"  TTS engine: {response.tts_engine}")
        except Exception as e:
            console.print(f"[dim]Could not get detailed status: {e}[/]")


@daemon_app.command("restart")
def daemon_restart(
    foreground: Annotated[
        bool,
        typer.Option("--foreground", "-f", help="Run in foreground after restart"),
    ] = False,
) -> None:
    """Restart the voxtype daemon."""
    from voxtype.daemon import get_daemon_status, start_daemon, stop_daemon

    status = get_daemon_status()
    if status.running:
        console.print(f"[dim]Stopping daemon (PID: {status.pid})...[/]")
        stop_daemon()

    console.print("[dim]Starting daemon...[/]")
    result = start_daemon(foreground=foreground)

    if result == 0 and not foreground:
        import time

        time.sleep(0.5)
        status = get_daemon_status()
        if status.running:
            console.print(f"[green]Daemon restarted[/] (PID: {status.pid})")
        else:
            console.print("[red]Daemon failed to start[/]")
            raise typer.Exit(1)


# =============================================================================
# Engine commands (new architecture)
# =============================================================================


@engine_app.command("start")
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
    """Start the VoxType engine.

    Foreground mode (default):
        voxtype engine start --keyboard    # Types what you say, listening immediately
        voxtype engine start --agents      # Agent mode, listening immediately

    Daemon mode (background):
        voxtype engine start -d --agents   # Background, models loaded, waiting for trigger

    In daemon mode, the engine preloads models but stays IDLE until activated
    via tray click, hotkey, or API call.
    """
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
    import os

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
    if not _check_required_models(config, for_command="engine"):
        raise typer.Exit(1)

    # Auto-detect hardware acceleration
    _auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

    # Auto-detect hotkey based on platform
    if config.hotkey.key == "KEY_SCROLLLOCK" and sys.platform == "darwin":
        config.hotkey.key = "KEY_RIGHTMETA"

    # Create AppController
    controller = AppController(config)

    if daemon:
        # Daemon mode: headless, no UI, no bindings, start_listening=False
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
            # Kill resource_tracker + os._exit to prevent leaked semaphore warnings
            import signal as sig

            try:
                from multiprocessing.resource_tracker import _resource_tracker

                tracker_pid: int | None = getattr(_resource_tracker, "_pid", None)
                if tracker_pid is not None:
                    os.kill(tracker_pid, sig.SIGKILL)
            except Exception:
                pass
            os._exit(0)
    else:
        # Foreground mode: AppController + StatusPanel UI
        import signal
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

        def _kill_resource_tracker() -> None:
            """Kill resource_tracker subprocess to prevent leaked semaphore warnings."""
            import signal as sig

            try:
                from multiprocessing.resource_tracker import _resource_tracker

                pid: int | None = getattr(_resource_tracker, "_pid", None)
                if pid is not None:
                    os.kill(pid, sig.SIGKILL)
            except Exception:
                pass

        shutdown_attempted = False

        if verbose:
            # Verbose mode: plain text logging, no Live panel
            import json
            import logging as _logging
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
                    _kill_resource_tracker()
                    os._exit(1)
                shutdown_attempted = True
                console.print("\n[yellow]Shutting down...[/]")
                def _force_exit() -> None:
                    _time.sleep(3)
                    _kill_resource_tracker()
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
            _kill_resource_tracker()
            os._exit(1 if init_error else 0)
        else:
            # Normal mode: StatusPanel with Rich Live
            from voxtype.ui.panel import StatusPanel

            # Run StatusPanel in main thread (polls /status, shows UI)
            panel = StatusPanel(console, base_url)

            def signal_handler(signum: int, frame: Any) -> None:
                nonlocal shutdown_attempted
                if shutdown_attempted:
                    _kill_resource_tracker()
                    os._exit(1)

                shutdown_attempted = True
                panel.stop()

                def force_exit() -> None:
                    import time

                    time.sleep(3)
                    _kill_resource_tracker()
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
                _kill_resource_tracker()
                os._exit(0)


@engine_app.command("stop")
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


@engine_app.command("status")
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


@app.command()
def speak(
    ctx: typer.Context,
    text: Annotated[
        str | None,
        typer.Argument(help="Text to speak (use '-' or omit to read from stdin)"),
    ] = None,
    language: Annotated[
        str | None,
        typer.Option("--language", "-l", help="Language code (en, it, de, etc.)"),
    ] = None,
    speed: Annotated[
        int | None,
        typer.Option("--speed", "-s", help="Speech speed in words per minute"),
    ] = None,
    engine: Annotated[
        str | None,
        typer.Option("--engine", "-e", help="TTS engine: espeak, say, piper, coqui, qwen3, outetts"),
    ] = None,
    voice: Annotated[
        str | None,
        typer.Option("--voice", "-v", help="Voice name (engine-specific)"),
    ] = None,
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress status messages (for pipe mode)"),
    ] = False,
    list_engines: Annotated[
        bool,
        typer.Option("--list-engines", help="List available TTS engines and exit"),
    ] = False,
    no_daemon: Annotated[
        bool,
        typer.Option("--no-daemon", help="Force in-process TTS (skip daemon even if running)"),
    ] = False,
) -> None:
    """Speak text using text-to-speech.

    Examples:
        voxtype speak "Hello world"
        echo "Hello world" | voxtype speak
        llm "Tell me a joke" | voxtype speak --engine say
        voxtype speak --list-engines
        voxtype speak "Hello" --no-daemon  # Force in-process
    """
    import sys

    from voxtype.config import TTSConfig, load_config
    from voxtype.tts import create_tts_engine

    # List engines mode
    if list_engines:
        console.print("[bold]Available TTS engines:[/]\n")
        engines_info = [
            ("espeak", "Basic TTS", "Many", "System: brew install espeak"),
            ("say", "macOS built-in", "Many", "macOS only"),
            ("piper", "Neural TTS", "Many", "pip: piper-tts"),
            ("coqui", "Neural TTS (XTTS)", "8+", "pip: TTS"),
            ("outetts", "Neural TTS (MLX)", "24", "Apple Silicon, pip: mlx-audio"),
            ("qwen3", "VyvoTTS (MLX)", "en only", "Apple Silicon, pip: mlx-audio"),
        ]
        for name, desc, langs, install in engines_info:
            console.print(f"  [cyan]{name:10}[/] {desc:20} Languages: {langs:8} ({install})")
        console.print("\n[dim]Use: voxtype speak \"text\" --engine <name>[/]")
        raise typer.Exit(0)

    # Load config
    config = load_config(config_file)

    # Read from stdin if no text provided or text is "-"
    if text is None or text == "-":
        if sys.stdin.isatty():
            # No pipe, no argument - show help
            import click
            click.echo(ctx.get_help())
            raise typer.Exit(0)
        text = sys.stdin.read().strip()
        if not text:
            # Empty pipe - also show help
            import click
            click.echo(ctx.get_help())
            raise typer.Exit(0)

    # Validate engine if provided
    valid_engines = ("espeak", "say", "piper", "coqui", "qwen3", "outetts")
    if engine is not None and engine not in valid_engines:
        console.print(f"[red]Error: Unknown TTS engine '{engine}'[/]")
        console.print(f"[dim]Available engines: {', '.join(valid_engines)}[/]")
        raise typer.Exit(1)

    # Build TTS config with CLI overrides
    tts_config = TTSConfig(
        engine=engine or config.tts.engine,  # type: ignore[arg-type]
        language=language or config.tts.language,
        speed=speed or config.tts.speed,
        voice=voice or config.tts.voice,
    )

    # Try to use daemon if available and not --no-daemon
    if not no_daemon:
        from voxtype.daemon.client import DaemonClient, is_daemon_running

        if is_daemon_running():
            try:
                client = DaemonClient()
                response = client.send_tts_request(
                    text=text,
                    engine=tts_config.engine,
                    language=tts_config.language,
                    voice=tts_config.voice if tts_config.voice else None,
                    speed=tts_config.speed,
                )

                if hasattr(response, "status") and response.status == "ok":
                    if not quiet:
                        console.print(f"[dim]Spoken via daemon ({response.duration_ms}ms)[/]")
                    return
                elif hasattr(response, "error"):
                    if not quiet:
                        console.print(f"[yellow]Daemon error: {response.error}[/]")
                    # Fall through to in-process TTS
            except Exception as e:
                if not quiet:
                    console.print(f"[yellow]Daemon unavailable: {e}[/]")
                # Fall through to in-process TTS

    # Fallback: in-process TTS
    try:
        tts = create_tts_engine(tts_config)
    except ValueError as e:
        from voxtype.utils.install_info import get_feature_install_message

        console.print(f"[red]{e}[/]")
        if tts_config.engine == "espeak":
            console.print("  Install: sudo apt install espeak-ng (Linux) or brew install espeak (macOS)")
        elif tts_config.engine in ("piper", "coqui"):
            console.print(get_feature_install_message(tts_config.engine))
        raise typer.Exit(1)

    if not quiet:
        console.print(f"[dim]Speaking ({tts.get_name()}): {text[:50]}{'...' if len(text) > 50 else ''}[/]")

    tts.speak(text)


@app.command()
def transcribe(
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Whisper model size (tiny/base/small/medium/large-v3)"),
    ] = None,
    language: Annotated[
        str | None,
        typer.Option("--language", "-l", help="Language code or 'auto'"),
    ] = None,
    no_hw_accel: Annotated[
        bool,
        typer.Option("--no-hw-accel", help="Disable hardware acceleration (force CPU)"),
    ] = False,
    silence_ms: Annotated[
        int,
        typer.Option("--silence-ms", "-s", help="Silence duration to end recording (ms)"),
    ] = 1200,
    max_duration: Annotated[
        int,
        typer.Option("--max-duration", "-d", help="Max recording duration in seconds"),
    ] = 60,
    output_file: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file (default: stdout)"),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress all status messages (pure pipe mode)"),
    ] = False,
    show_text: Annotated[
        bool,
        typer.Option("--show-text", "-t", help="Show transcribed text on stderr before output"),
    ] = True,
) -> None:
    """Record and transcribe audio to text (one-shot).

    Perfect for piping to other tools:

        voxtype transcribe | llm "respond to this"

        llm "$(voxtype transcribe)"

    Status messages go to stderr, transcription goes to stdout.
    """
    import io
    import os

    config = load_config(config_file)

    # Apply CLI override for hw_accel
    if no_hw_accel:
        config.stt.hw_accel = False

    # Suppress progress bars and loading messages unless verbose
    # Redirect stderr during model loading to suppress progress bars
    if not quiet:
        print("[Loading model...]", file=sys.stderr)

    # Suppress tqdm and other progress output during load
    old_stderr = sys.stderr
    if not os.environ.get("VOXTYPE_VERBOSE"):
        sys.stderr = io.StringIO()

    try:
        # Auto-detect hardware acceleration (unless hw_accel=false)
        _auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

        # Apply CLI overrides
        if model:
            config.stt.model = model
        if language:
            config.stt.language = language

        # Create STT engine - use MLX on Apple Silicon if hw_accel enabled
        from voxtype.utils.hardware import is_mlx_available
        use_mlx = config.stt.hw_accel and is_mlx_available()

        from voxtype.stt.base import STTEngine
        stt_engine: STTEngine
        if use_mlx:
            from voxtype.stt.mlx_whisper import MLXWhisperEngine
            stt_engine = MLXWhisperEngine()
        else:
            from voxtype.stt.faster_whisper import FasterWhisperEngine
            stt_engine = FasterWhisperEngine()

        stt_engine.load_model(
            config.stt.model,
            device=config.stt.device,
            compute_type=config.stt.compute_type,
        )
    finally:
        sys.stderr = old_stderr

    # Create transcriber and run
    from voxtype.core.transcriber import OneShotTranscriber

    transcriber = OneShotTranscriber(
        config=config,
        stt_engine=stt_engine,
        silence_ms=silence_ms,
        max_duration=max_duration,
        quiet=quiet,
    )

    try:
        text = transcriber.record_and_transcribe()

        if text and show_text and not quiet:
            # Show what was transcribed on stderr
            print(f"\n> {text}\n", file=sys.stderr)

        if output_file:
            output_file.write_text(text)
            if not quiet:
                print(f"[Saved to {output_file}]", file=sys.stderr)
        else:
            # Raw output to stdout for piping
            print(text, end="")
    except KeyboardInterrupt:
        if not quiet:
            print("\n[Cancelled]", file=sys.stderr)
        raise typer.Exit(1)


@app.command(
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False}
)
def execute(
    ctx: typer.Context,
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Whisper model size"),
    ] = None,
    language: Annotated[
        str | None,
        typer.Option("--language", "-l", help="Language code or 'auto'"),
    ] = None,
    one_shot: Annotated[
        bool,
        typer.Option("--one-shot", "-1", help="Single transcription then exit"),
    ] = True,
    silence_ms: Annotated[
        int,
        typer.Option("--silence-ms", "-s", help="Silence duration to end recording (ms)"),
    ] = 1200,
    no_hw_accel: Annotated[
        bool,
        typer.Option("--no-hw-accel", help="Disable hardware acceleration"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show status messages"),
    ] = False,
) -> None:
    """Execute a command with transcribed speech.

    Use {{text}} as placeholder for the transcribed text.

    Examples:
        voxtype execute -- llm "{{text}}"
        voxtype execute -- llm "{{text}}" | voxtype speak
        voxtype execute -- echo "You said: {{text}}"

    For continuous voice assistant (loop mode):
        voxtype execute --no-one-shot -- llm "{{text}}" | voxtype speak
    """
    import io
    import os
    import shlex
    import subprocess

    # Get command from extra args (everything after --)
    cmd_parts = ctx.args
    if not cmd_parts:
        console.print("[red]No command provided. Usage: voxtype execute -- llm \"{{text}}\"[/]")
        raise typer.Exit(1)

    # Join command parts back together
    cmd_template = " ".join(cmd_parts)

    if "{{text}}" not in cmd_template:
        console.print("[yellow]Warning: No {{text}} placeholder found in command[/]")

    config = load_config(config_file)

    if no_hw_accel:
        config.stt.hw_accel = False

    # Load STT engine once
    if verbose:
        print("[Loading model...]", file=sys.stderr)

    old_stderr = sys.stderr
    if not os.environ.get("VOXTYPE_VERBOSE"):
        sys.stderr = io.StringIO()

    try:
        _auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

        if model:
            config.stt.model = model
        if language:
            config.stt.language = language

        from voxtype.utils.hardware import is_mlx_available
        use_mlx = config.stt.hw_accel and is_mlx_available()

        from voxtype.stt.base import STTEngine
        stt_engine: STTEngine
        if use_mlx:
            from voxtype.stt.mlx_whisper import MLXWhisperEngine
            stt_engine = MLXWhisperEngine()
        else:
            from voxtype.stt.faster_whisper import FasterWhisperEngine
            stt_engine = FasterWhisperEngine()

        stt_engine.load_model(
            config.stt.model,
            device=config.stt.device,
            compute_type=config.stt.compute_type,
        )
    finally:
        sys.stderr = old_stderr

    from voxtype.core.transcriber import OneShotTranscriber

    while True:
        transcriber = OneShotTranscriber(
            config=config,
            stt_engine=stt_engine,
            silence_ms=silence_ms,
            max_duration=config.audio.max_duration,
            quiet=not verbose,
        )

        try:
            if verbose:
                print("[Listening...]", file=sys.stderr)

            text = transcriber.record_and_transcribe()

            if not text:
                if verbose:
                    print("[No speech detected]", file=sys.stderr)
                if one_shot:
                    break
                continue

            if verbose:
                print(f"> {text}", file=sys.stderr)

            # Substitute {{text}} in command (properly quoted for shell)
            import shlex
            final_cmd = cmd_template.replace("{{text}}", shlex.quote(text))

            if verbose:
                print(f"[Executing: {final_cmd[:60]}...]", file=sys.stderr)

            # Execute command with shell=True to support pipes
            result = subprocess.run(
                final_cmd,
                shell=True,
                text=True,
            )

            if one_shot:
                raise typer.Exit(result.returncode)

        except KeyboardInterrupt:
            if verbose:
                print("\n[Stopped]", file=sys.stderr)
            raise typer.Exit(0)


@app.command()
def devices(
    set_hotkey: Annotated[
        bool,
        typer.Option("--set-hotkey", "-k", help="Set selected device as hotkey device"),
    ] = False,
    hid: Annotated[
        bool,
        typer.Option("--hid", "-H", help="List HID devices (for device profiles)"),
    ] = False,
) -> None:
    """List input devices and optionally configure hotkey device.

    Shows all input devices. Use --hid to list HID devices with vendor/product IDs
    for creating device profiles.

    Example:
        voxtype devices                    # List input devices
        voxtype devices --hid              # List HID devices with IDs
        voxtype devices --set-hotkey       # Select device for hotkey
    """
    if hid:
        _list_hid_devices()
        return

    if sys.platform == "linux":
        _list_evdev_devices(set_hotkey)
    else:
        # macOS: show HID devices by default
        _list_hid_devices()


def _list_hid_devices() -> None:
    """List HID devices with vendor/product IDs."""
    try:
        import hid
        devices_list = hid.enumerate()
    except ImportError:
        try:
            # Try hidapi package (cython-based, bundles native lib)
            import hidapi
            devices_list = [
                {
                    "vendor_id": d.vendor_id,
                    "product_id": d.product_id,
                    "manufacturer_string": d.manufacturer_string,
                    "product_string": d.product_string,
                }
                for d in hidapi.enumerate()
            ]
        except ImportError:
            from voxtype.utils.install_info import get_feature_install_message

            console.print("[red]hidapi package not installed[/]")
            console.print("This should be installed automatically on macOS.")
            console.print(get_feature_install_message("hidapi"))
            raise typer.Exit(1)

    if not devices_list:
        console.print("[yellow]No HID devices found[/]")
        raise typer.Exit(1)

    # Group by vendor_id/product_id to deduplicate interfaces
    seen = set()
    unique_devices = []
    for dev in devices_list:
        key = (dev["vendor_id"], dev["product_id"])
        if key not in seen and key != (0, 0):
            seen.add(key)
            unique_devices.append(dev)

    # Sort by product name
    unique_devices.sort(key=lambda d: (d.get("product_string") or "").lower())

    table = Table(title="HID Devices", show_header=True, header_style="bold", expand=False)
    table.add_column("Vendor ID", style="cyan", width=10)
    table.add_column("Product ID", style="cyan", width=10)
    table.add_column("Manufacturer", width=20)
    table.add_column("Product", style="green", width=30)

    for dev in unique_devices:
        vendor_id = f"0x{dev['vendor_id']:04x}"
        product_id = f"0x{dev['product_id']:04x}"
        manufacturer = dev.get("manufacturer_string") or "[dim]—[/]"
        product = dev.get("product_string") or "[dim]Unknown[/]"

        table.add_row(vendor_id, product_id, manufacturer, product)

    console.print(table)
    console.print()
    console.print("[dim]To use a device, create ~/.config/voxtype/devices/<name>.toml:[/]")
    console.print()
    console.print('[dim]  vendor_id = 0x????[/]')
    console.print('[dim]  product_id = 0x????[/]')
    console.print('[dim]  [bindings][/]')
    console.print('[dim]  KEY_PAGEUP = "project-prev"[/]')
    console.print('[dim]  KEY_PAGEDOWN = "project-next"[/]')
    console.print('[dim]  KEY_B = "toggle-listening"[/]')


def _list_evdev_devices(set_hotkey: bool) -> None:
    """List evdev devices (Linux only)."""
    try:
        import evdev
    except ImportError:
        from voxtype.utils.install_info import get_feature_install_message

        console.print("[red]evdev not installed[/]")
        console.print(get_feature_install_message("evdev"))
        raise typer.Exit(1)

    # Collect all devices with their info
    devices_info: list[dict[str, Any]] = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
            caps = device.capabilities().get(evdev.ecodes.EV_KEY, [])
            has_scroll = evdev.ecodes.KEY_SCROLLLOCK in caps
            has_keys = len(caps) > 0
            name = device.name
            is_keyboard = "keyboard" in name.lower()
            device.close()

            devices_info.append({
                "path": path,
                "name": name,
                "has_keys": has_keys,
                "has_scroll": has_scroll,
                "is_keyboard": is_keyboard,
            })
        except Exception:
            continue

    # Sort: keyboards first, then by name
    devices_info.sort(key=lambda d: (not d["is_keyboard"], d["name"].lower()))

    if not devices_info:
        console.print("[yellow]No input devices found[/]")
        raise typer.Exit(1)

    # Display table
    table = Table(title="Input Devices", show_header=True, header_style="bold", expand=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Device Name", style="cyan")
    table.add_column("Keys", justify="center", width=6)
    table.add_column("ScrollLock", justify="center", width=10)
    table.add_column("Type", width=12)

    # Add option 0 for auto-detect
    if set_hotkey:
        table.add_row("0", "[yellow](auto-detect)[/]", "—", "—", "—")

    for i, dev in enumerate(devices_info, 1):
        keys_icon = "[green]✓[/]" if dev["has_keys"] else "[dim]—[/]"
        scroll_icon = "[green]✓[/]" if dev["has_scroll"] else "[dim]—[/]"
        dev_type = "[cyan]Keyboard[/]" if dev["is_keyboard"] else "[dim]Other[/]"

        table.add_row(str(i), dev["name"], keys_icon, scroll_icon, dev_type)

    console.print(table)

    # If setting hotkey, prompt for selection
    if set_hotkey:
        console.print()
        prompt = f"Select device for hotkey [0=auto-detect, 1-{len(devices_info)}]"

        try:
            choice = typer.prompt(prompt, type=int)
            if choice < 0 or choice > len(devices_info):
                console.print("[red]Invalid selection[/]")
                raise typer.Exit(1)

            if choice == 0:
                set_config_value("hotkey.device", "")
                console.print("[green]✓[/] Hotkey device cleared (auto-detect)")
            else:
                selected = devices_info[choice - 1]
                set_config_value("hotkey.device", selected["name"])
                console.print(f"[green]✓[/] Hotkey device set to: [cyan]{selected['name']}[/]")

        except (ValueError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled[/]")
            raise typer.Exit(0)
    else:
        console.print("\n[dim]Use --set-hotkey to configure a device[/]")
        console.print("[dim]Use --hid to list HID devices for device profiles[/]")


@app.command()
def cmd(
    ctx: typer.Context,
    command: Annotated[str | None, typer.Argument(help="Command to send (e.g., toggle-listening)")] = None,
) -> None:
    """Send a command to a running voxtype instance.

    Used by external tools (like Karabiner-Elements) to control voxtype.

    Available commands:
        toggle-listening, listening-on, listening-off,
        toggle-mode, project-next, project-prev,
        discard, repeat

    Example:
        voxtype cmd toggle-listening
        voxtype cmd project-next
    """
    if command is None:
        import click
        click.echo(ctx.get_help())
        raise typer.Exit(0)

    import socket

    from voxtype.utils.platform import get_socket_dir

    socket_path = str(get_socket_dir() / "control.sock")

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_path)
        sock.send(command.encode())
        sock.close()
        # Silent success for scripting
    except FileNotFoundError:
        console.print("[red]voxtype is not running (socket not found)[/]")
        console.print("[dim]Start voxtype first: voxtype listen[/]")
        raise typer.Exit(1)
    except ConnectionRefusedError:
        console.print("[red]voxtype is not accepting commands[/]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command()
def backends() -> None:
    """List available device input backends.

    Shows which backends are available on this system for
    handling dedicated input devices (presenter remotes, macro pads).
    """
    from voxtype.input.backends import get_available_backends

    available = get_available_backends()

    if not available:
        from voxtype.utils.install_info import get_feature_install_message

        console.print("[yellow]No device backends available[/]")
        console.print()
        console.print("[dim]Install dependencies:[/]")
        console.print(f"  macOS: {get_feature_install_message('hidapi').strip()} or brew install --cask karabiner-elements")
        console.print(f"  Linux: {get_feature_install_message('evdev').strip()}")
        raise typer.Exit(1)

    table = Table(title="Device Backends", show_header=True, header_style="bold", expand=False)
    table.add_column("Backend", style="cyan")
    table.add_column("Grab", justify="center")
    table.add_column("Platform")
    table.add_column("Status", justify="center")

    backend_info = {
        "evdev": ("Linux", "Native evdev with exclusive grab"),
        "hidapi": ("All", "Direct HID access, no grab"),
        "karabiner": ("macOS", "Karabiner-Elements with exclusive grab"),
    }

    for name in ["evdev", "karabiner", "hidapi"]:
        platform, desc = backend_info.get(name, ("?", "?"))
        is_available = name in available

        if is_available:
            # Get grab support
            if name == "evdev":
                from voxtype.input.backends.evdev_backend import EvdevBackend
                grab = "[green]✓[/]" if EvdevBackend().supports_grab else "[dim]—[/]"
            elif name == "karabiner":
                from voxtype.input.backends.karabiner_backend import KarabinerBackend
                grab = "[green]✓[/]" if KarabinerBackend().supports_grab else "[dim]—[/]"
            else:
                from voxtype.input.backends.hidapi_backend import HIDAPIBackend
                grab = "[green]✓[/]" if HIDAPIBackend().supports_grab else "[dim]—[/]"

            status = "[green]Available[/]"
        else:
            grab = "[dim]—[/]"
            status = "[dim]Not installed[/]"

        table.add_row(name, grab, platform, status)

    console.print(table)
    console.print()
    console.print("[dim]Grab = exclusive device access (recommended for presenter remotes)[/]")


@app.command(
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False}
)
def agent(
    ctx: typer.Context,
    agent_id: Annotated[
        str | None,
        typer.Argument(help="Agent ID (e.g., 'claude')"),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress info messages"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Log full text in session file (not truncated)"),
    ] = False,
    server: Annotated[
        str | None,
        typer.Option("--server", "-s", help="Engine HTTP server URL (default: from config)"),
    ] = None,
) -> None:
    """Run a command with voxtype voice input via OpenVIP SSE.

    Connects to the engine HTTP server via SSE to receive voice transcriptions.
    The SSE connection automatically registers the agent with the engine.

    Example:

        # Terminal 1: Start listening with agent mode
        voxtype listen --agents

        # Terminal 2: Start the agent wrapper
        voxtype agent claude -- claude
    """
    # Show help if no agent_id
    if agent_id is None:
        import click
        click.echo(ctx.get_help())
        raise typer.Exit(0)

    from voxtype.agent import run_agent
    from voxtype.config import load_config

    # Resolve server URL: --server flag > config > default
    if server is None:
        config = load_config()
        server = config.client.url

    # With allow_interspersed_args=False, flags after positional args go to ctx.args.
    # Extract our own flags before passing the rest as the command.
    args = list(ctx.args)
    own_flags_to_remove: set[int] = set()
    show_status_bar = True
    for i, arg in enumerate(args):
        if arg in ("--verbose", "-v"):
            verbose = True
            own_flags_to_remove.add(i)
        elif arg in ("--quiet", "-q"):
            quiet = True
            own_flags_to_remove.add(i)
        elif arg == "--no-status-bar":
            show_status_bar = False
            own_flags_to_remove.add(i)
        elif arg in ("--server", "-s") and i + 1 < len(args):
            server = args[i + 1]
            own_flags_to_remove.add(i)
            own_flags_to_remove.add(i + 1)
        elif arg == "--":
            own_flags_to_remove.add(i)

    command = [arg for i, arg in enumerate(args) if i not in own_flags_to_remove]
    if not command:
        console.print("[red]Error: No command specified[/]")
        console.print()
        console.print("[dim]Usage: voxtype agent AGENT_ID -- COMMAND...[/]")
        console.print("[dim]Example: voxtype agent claude -- claude[/]")
        raise typer.Exit(1)

    exit_code = run_agent(
        agent_id, command, quiet=quiet, verbose=verbose,
        base_url=server, status_bar=show_status_bar,
    )
    raise typer.Exit(exit_code)


# Log subcommand for viewing logs
log_app = typer.Typer(help="View voxtype logs", no_args_is_help=True)
app.add_typer(log_app, name="log")


def _tail_log(log_path: Path, follow: bool, json_output: bool, lines: int = 20) -> None:
    """Tail a log file with optional follow mode.

    Args:
        log_path: Path to the JSONL log file.
        follow: If True, continuously follow the file.
        json_output: If True, output raw JSON; otherwise format for readability.
        lines: Number of lines to show initially.
    """
    import json
    import time
    from datetime import datetime

    if not log_path.exists():
        console.print(f"[yellow]Log file not found: {log_path}[/]")
        console.print("[dim]Start voxtype first to create logs.[/]")
        raise typer.Exit(1)

    def format_line(line: str) -> str | None:
        """Format a JSONL line for display."""
        try:
            entry = json.loads(line)
            # Support both "ts" (msg events) and "timestamp" (session events)
            ts = entry.get("ts") or entry.get("timestamp", "")
            level = entry.get("level", "INFO")
            event = entry.get("event", "")

            # Parse and format timestamp
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    ts_str = dt.strftime("%H:%M:%S")
                except Exception:
                    ts_str = ts[:8]
            else:
                ts_str = "??:??:??"

            # Color by level
            level_colors = {"ERROR": "red", "INFO": "green", "DEBUG": "dim"}
            level_color = level_colors.get(level, "white")

            # Format event-specific info
            extra = ""
            if event == "session_start":
                # Support both listen logs and session logs
                version = entry.get("version") or entry.get("voxtype_version", "?")
                model = entry.get("stt_model")
                agent_id = entry.get("agent_id")
                if agent_id:
                    extra = f"v{version} agent={agent_id}"
                elif model:
                    extra = f"v{version} model={model}"
                else:
                    extra = f"v{version}"
            elif event == "session_end":
                keystrokes = entry.get("total_keystrokes", 0)
                exit_code = entry.get("exit_code", "?")
                extra = f"exit={exit_code} keystrokes={keystrokes}"
            elif event in ("msg_read", "msg_sent"):
                text = entry.get("text", "")
                # Show up to 80 chars
                display_text = text[:80]
                if len(text) > 80:
                    display_text += "..."
                extra = display_text.replace("\n", "\\n")
            elif event == "transcription":
                chars = entry.get("chars", 0)
                words = entry.get("words", 0)
                duration = entry.get("duration_ms", 0)
                text = entry.get("text")  # May be None (privacy mode)
                if text:
                    # Verbose mode - show text
                    display = text[:60].replace("\n", "\\n")
                    if len(text) > 60:
                        display += "..."
                    extra = f'{duration:.0f}ms "{display}"'
                else:
                    # Privacy mode - show only metadata
                    extra = f"{words}w {chars}c {duration:.0f}ms"
            elif event == "transcription_text":
                # Legacy format (kept for old logs)
                text = entry.get("text", "")[:60]
                extra = f'"{text}"' + ("..." if len(entry.get("text", "")) > 60 else "")
            elif event == "injection":
                chars = entry.get("chars", 0)
                method = entry.get("method", "?")
                trigger = entry.get("submit_trigger")
                text = entry.get("text")  # May be None (privacy mode)
                if text:
                    # Verbose mode - show text
                    display = text[:60].replace("\n", "\\n")
                    if len(text) > 60:
                        display += "..."
                    extra = f'via {method} "{display}"'
                else:
                    # Privacy mode - show only metadata
                    extra = f"{chars}c via {method}"
                # Always show trigger (even in privacy mode)
                if trigger:
                    conf = entry.get("submit_confidence", 0)
                    extra += f' [SUBMIT: "{trigger}" {conf:.0%}]'
            elif event == "state_change":
                old = entry.get("old_state", "?")
                new = entry.get("new_state", "?")
                trigger = entry.get("trigger", "?")
                extra = f"{old} -> {new} ({trigger})"
            elif event == "error":
                error = entry.get("error", "")[:50]
                extra = error
            elif event == "vad":
                vad_type = entry.get("type", "?")
                duration = entry.get("duration_ms")
                extra = vad_type + (f" {duration:.0f}ms" if duration else "")

            return f"[dim]{ts_str}[/] [{level_color}]{level:5}[/] [cyan]{event:20}[/] {extra}"
        except json.JSONDecodeError:
            return None

    # Read existing lines
    with open(log_path) as f:
        all_lines = f.readlines()

    # Show last N lines
    start_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

    for line in start_lines:
        line = line.strip()
        if not line:
            continue
        if json_output:
            print(line)
        else:
            formatted = format_line(line)
            if formatted:
                console.print(formatted)

    if not follow:
        return

    # Follow mode: watch for new lines
    console.print("[dim]--- Following (Ctrl+C to stop) ---[/]")

    try:
        with open(log_path) as f:
            # Seek to end
            f.seek(0, 2)

            while True:
                line = f.readline()
                if line:
                    line = line.strip()
                    if json_output:
                        print(line)
                    else:
                        formatted = format_line(line)
                        if formatted:
                            console.print(formatted)
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/]")


@log_app.command("listen")
def log_listen(
    follow: Annotated[
        bool,
        typer.Option("--follow", "-f", help="Follow log output (like tail -f)"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output raw JSON lines"),
    ] = False,
    lines: Annotated[
        int,
        typer.Option("--lines", "-n", help="Number of lines to show"),
    ] = 20,
) -> None:
    """View logs from voxtype listen sessions.

    Shows recent log entries from ~/.local/share/voxtype/logs/listen.jsonl

    Examples:
        voxtype log listen              # Show last 20 entries
        voxtype log listen -f           # Follow live
        voxtype log listen -n 50        # Show last 50 entries
        voxtype log listen --json       # Output raw JSON
    """
    from voxtype.logging.jsonl import get_default_log_path

    log_path = get_default_log_path("listen")
    _tail_log(log_path, follow, json_output, lines)


@log_app.command("engine")
def log_engine(
    follow: Annotated[
        bool,
        typer.Option("--follow", "-f", help="Follow log output (like tail -f)"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output raw JSON lines"),
    ] = False,
    lines: Annotated[
        int,
        typer.Option("--lines", "-n", help="Number of lines to show"),
    ] = 20,
) -> None:
    """View logs from voxtype engine sessions.

    Shows recent log entries from ~/.local/share/voxtype/logs/engine.jsonl

    Use --verbose flag when starting engine to see full text in logs.

    Examples:
        voxtype log engine              # Show last 20 entries
        voxtype log engine -f           # Follow live
        voxtype log engine -n 50        # Show last 50 entries
        voxtype log engine --json       # Output raw JSON
    """
    from voxtype.logging.jsonl import get_default_log_path

    log_path = get_default_log_path("engine")
    _tail_log(log_path, follow, json_output, lines)


@log_app.command("agent")
def log_agent(
    ctx: typer.Context,
    agent_name: Annotated[
        str | None,
        typer.Argument(help="Agent name to view logs for"),
    ] = None,
    follow: Annotated[
        bool,
        typer.Option("--follow", "-f", help="Follow log output (like tail -f)"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output raw JSON lines"),
    ] = False,
    lines: Annotated[
        int,
        typer.Option("--lines", "-n", help="Number of lines to show"),
    ] = 20,
) -> None:
    """View logs for a specific agent.

    Shows recent log entries from ~/.local/share/voxtype/logs/agent.<name>.jsonl

    Examples:
        voxtype log agent claude        # Show logs for claude agent
        voxtype log agent claude -f     # Follow live
    """
    if agent_name is None:
        import click
        click.echo(ctx.get_help())
        raise typer.Exit(0)

    from voxtype.logging.jsonl import get_default_log_path

    log_path = get_default_log_path(f"agent.{agent_name}")
    _tail_log(log_path, follow, json_output, lines)


@log_app.command("path")
def log_path_cmd(
    agent_name: Annotated[
        str | None,
        typer.Argument(help="Agent name (optional)"),
    ] = None,
) -> None:
    """Show log file path.

    Examples:
        voxtype log path           # Show listen log path
        voxtype log path claude    # Show claude agent log path
    """
    from voxtype.logging.jsonl import get_default_log_path

    if agent_name:
        log_path = get_default_log_path(f"agent.{agent_name}")
    else:
        log_path = get_default_log_path("listen")

    console.print(str(log_path))


@log_app.command("list")
def log_list() -> None:
    """List available log files.

    Shows all log files in ~/.local/share/voxtype/logs/
    """
    from voxtype.logging.jsonl import DEFAULT_LOG_DIR

    if not DEFAULT_LOG_DIR.exists():
        console.print(f"[yellow]Log directory not found: {DEFAULT_LOG_DIR}[/]")
        console.print("[dim]Start voxtype first to create logs.[/]")
        raise typer.Exit(1)

    log_files = list(DEFAULT_LOG_DIR.glob("*.jsonl"))

    if not log_files:
        console.print("[yellow]No log files found.[/]")
        raise typer.Exit(0)

    # Sort by modification time (newest first)
    log_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("Log File", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Last Modified")

    for log_file in log_files:
        stat = log_file.stat()
        size = stat.st_size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / 1024 / 1024:.1f} MB"

        from datetime import datetime

        mtime = datetime.fromtimestamp(stat.st_mtime)
        mtime_str = mtime.strftime("%Y-%m-%d %H:%M")

        # Extract name from filename
        name = log_file.stem  # e.g., "listen" or "agent.claude"
        table.add_row(name, size_str, mtime_str)

    console.print(table)
    console.print(f"\n[dim]Log directory: {DEFAULT_LOG_DIR}[/]")


@log_app.command("session")
def log_session(
    ctx: typer.Context,
    agent_id: Annotated[
        str | None,
        typer.Argument(help="Agent ID to view session for"),
    ] = None,
    follow: Annotated[
        bool,
        typer.Option("--follow", "-f", help="Follow log output (like tail -f)"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output raw JSON lines"),
    ] = False,
    lines: Annotated[
        int,
        typer.Option("--lines", "-n", help="Number of lines to show"),
    ] = 20,
) -> None:
    """View session log for an agent.

    Shows the most recent session file from ~/.local/share/voxtype/sessions/

    Examples:
        voxtype log session claude        # Show latest claude session
        voxtype log session claude -f     # Follow live
        voxtype log session claude -n 50  # Show last 50 lines
    """
    if agent_id is None:
        import click
        click.echo(ctx.get_help())
        raise typer.Exit(0)

    from pathlib import Path

    sessions_dir = Path.home() / ".local" / "share" / "voxtype" / "sessions"

    if not sessions_dir.exists():
        console.print(f"[yellow]Sessions directory not found: {sessions_dir}[/]")
        raise typer.Exit(1)

    # Find session files for this agent (format: YYYY-MM-DD_HH-MM-SS_voxtype-X.Y.Z_AGENT.session.jsonl)
    pattern = f"*_{agent_id}.session.jsonl"
    session_files = list(sessions_dir.glob(pattern))

    if not session_files:
        console.print(f"[yellow]No sessions found for agent: {agent_id}[/]")
        raise typer.Exit(1)

    # Sort by name (contains timestamp) and get the latest
    session_files.sort(reverse=True)
    latest_session = session_files[0]

    if not json_output:
        console.print(f"[dim]Session: {latest_session}[/]")

    _tail_log(latest_session, follow, json_output, lines)


def _load_model_registry() -> dict:
    """Load model registry from JSON file."""
    import json
    from pathlib import Path

    models_file = Path(__file__).parent / "models.json"
    if models_file.exists():
        with open(models_file) as f:
            return json.load(f)
    return {}


_MODEL_REGISTRY: dict | None = None


def _get_model_registry() -> dict:
    """Get model registry (lazy loaded)."""
    global _MODEL_REGISTRY
    if _MODEL_REGISTRY is None:
        _MODEL_REGISTRY = _load_model_registry()
    return _MODEL_REGISTRY


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    else:
        return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"


def _get_configured_models(config=None) -> dict[str, str]:
    """Get model names that are configured to be used.

    Returns:
        Dict mapping model registry key to usage type (stt, realtime, tts).
    """
    if config is None:
        config = load_config()

    configured: dict[str, str] = {}
    registry = _get_model_registry()

    # STT model: map config value to registry key
    # e.g., "large-v3-turbo" -> "whisper-large-v3-turbo"
    stt_model = config.stt.model
    stt_key = f"whisper-{stt_model}"
    if stt_key in registry:
        configured[stt_key] = "stt"

    # Realtime STT model
    realtime_model = config.stt.realtime_model
    realtime_key = f"whisper-{realtime_model}"
    if realtime_key in registry:
        if realtime_key in configured:
            configured[realtime_key] = "stt+realtime"
        else:
            configured[realtime_key] = "realtime"

    # TTS model: find model by engine
    # e.g., "qwen3" -> "vyvotts-4bit", "outetts" -> "outetts"
    tts_engine = config.tts.engine
    if tts_engine in ("qwen3", "outetts"):
        for name, info in registry.items():
            if info.get("engine") == tts_engine:
                configured[name] = "tts"
                break

    return configured



def _check_required_models(config=None, for_command: str = "listen") -> bool:
    """Check if required models are cached.

    Args:
        config: Config object (loaded if None)
        for_command: Command name for error message

    Returns:
        True if all required models are cached, False otherwise.
    """
    from voxtype.utils.hf_download import is_repo_cached

    if config is None:
        config = load_config()

    configured = _get_configured_models(config)
    registry = _get_model_registry()
    missing = []

    for name in configured.keys():
        if name in registry:
            info = registry[name]
            check_file = info.get("check_file", "config.json")
            if not is_repo_cached(info["repo"], check_file):
                missing.append(name)

    if missing:
        console.print(f"[red]Missing required models for '{for_command}':[/]")
        for name in missing:
            console.print(f"  [red]{name}[/]")
        console.print()
        _show_models_list(config)
        console.print()
        console.print("[bold]Download missing models:[/]")
        console.print("  [cyan]voxtype models resolve[/]")
        return False

    return True


def _show_models_list(config=None) -> None:
    """Show models list with configured status highlighting.

    - Green: configured AND cached
    - Red: configured but NOT cached
    - Normal: not configured
    """
    from voxtype.utils.hf_download import get_cache_size, is_repo_cached

    if config is None:
        config = load_config()

    configured = _get_configured_models(config)

    table = Table(
        title="Models",
        show_header=True,
        header_style="bold",
        expand=False,
    )
    table.add_column("Model", no_wrap=True)
    table.add_column("Type", width=4)
    table.add_column("Use", width=12)
    table.add_column("Status", justify="center")
    table.add_column("Size", justify="right")

    for name, info in _get_model_registry().items():
        repo = info["repo"]
        model_type = info["type"].upper()
        usage = configured.get(name, "")

        # Check if cached
        check_file = info.get("check_file", "config.json")
        cached = is_repo_cached(repo, check_file)

        # Determine colors based on configured + cached state
        if usage:
            if cached:
                # Configured and cached = green
                name_style = "[green]"
                status = "[green]cached[/]"
                use_str = f"[green]{usage}[/]"
            else:
                # Configured but not cached = red
                name_style = "[red]"
                status = "[red]MISSING[/]"
                use_str = f"[red]{usage}[/]"
        else:
            # Not configured = normal/dim
            name_style = "[dim]"
            status = "[dim]cached[/]" if cached else "[dim]—[/]"
            use_str = ""

        # Size
        if cached:
            cache_size = get_cache_size(repo)
            size_str = _format_size(cache_size) if cache_size > 0 else f"~{info['size_gb']:.1f} GB"
        else:
            size_str = f"~{info['size_gb']:.1f} GB"

        table.add_row(
            f"{name_style}{name}[/]",
            model_type,
            use_str,
            status,
            size_str,
        )

    console.print(table)


@models_app.command("list")
def models_list() -> None:
    """List available models and their cache status.

    Shows STT (Whisper) and TTS models with download status.
    Configured models shown in green (cached) or red (missing).
    """
    _show_models_list()
    console.print()
    console.print("[dim]Use:      voxtype models use <model> [--realtime|--tts][/]")
    console.print("[dim]Resolve:  voxtype models resolve[/]")
    console.print("[dim]Download: voxtype models download <model>[/]")


@models_app.command("use")
def models_use(
    ctx: typer.Context,
    model: Annotated[str | None, typer.Argument(help="Model name to use")] = None,
    realtime: Annotated[
        bool,
        typer.Option("--realtime", "-r", help="Set as realtime STT model"),
    ] = False,
    tts: Annotated[
        bool,
        typer.Option("--tts", "-t", help="Set as TTS model"),
    ] = False,
) -> None:
    """Set which model to use for STT or TTS.

    By default sets the STT model. Use flags for other types.

    Examples:
        voxtype models use large-v3-turbo           # Set STT model
        voxtype models use tiny --realtime          # Set realtime STT model
        voxtype models use vyvotts-4bit --tts       # Set TTS model
    """
    if model is None:
        import click
        click.echo(ctx.get_help())
        raise typer.Exit(0)

    registry = _get_model_registry()

    if tts:
        # TTS: find by model name or engine
        if model in registry and registry[model]["type"] == "tts":
            engine = registry[model].get("engine", model)
            set_config_value("tts.engine", engine)
            console.print(f"[green]✓[/] TTS set to [cyan]{engine}[/] (model: {model})")
        elif model in ("espeak", "say", "piper", "coqui", "qwen3", "outetts"):
            set_config_value("tts.engine", model)
            console.print(f"[green]✓[/] TTS engine set to [cyan]{model}[/]")
        else:
            console.print(f"[red]Unknown TTS model or engine: {model}[/]")
            console.print("[dim]Available: espeak, say, piper, coqui, qwen3, outetts[/]")
            raise typer.Exit(1)
        return

    # STT model (default or --realtime)
    # Accept both "large-v3-turbo" and "whisper-large-v3-turbo"
    stt_model = model.replace("whisper-", "") if model.startswith("whisper-") else model
    stt_key = f"whisper-{stt_model}"

    if stt_key not in registry:
        console.print(f"[red]Unknown STT model: {model}[/]")
        console.print("[dim]Available: tiny, base, small, medium, large-v3, large-v3-turbo[/]")
        raise typer.Exit(1)

    if realtime:
        set_config_value("stt.realtime_model", stt_model)
        console.print(f"[green]✓[/] Realtime STT set to [cyan]{stt_model}[/]")
    else:
        set_config_value("stt.model", stt_model)
        console.print(f"[green]✓[/] STT set to [cyan]{stt_model}[/]")


@models_app.command("resolve")
def models_resolve() -> None:
    """Download all configured models that are missing.

    Automatically downloads models needed for your current configuration.

    Example:
        voxtype models resolve
    """
    from huggingface_hub import snapshot_download

    from voxtype.utils.hf_download import download_with_progress, is_repo_cached

    config = load_config()
    configured = _get_configured_models(config)
    registry = _get_model_registry()

    # Find missing models
    missing: list[str] = []
    for name in configured.keys():
        if name in registry:
            info = registry[name]
            check_file = info.get("check_file", "config.json")
            if not is_repo_cached(info["repo"], check_file):
                missing.append(name)

    if not missing:
        console.print("[green]All configured models are already cached![/]")
        _show_models_list(config)
        raise typer.Exit(0)

    console.print(f"[bold]Downloading {len(missing)} missing model(s)...[/]\n")

    for name in missing:
        info = registry[name]
        repo: str = info["repo"]

        console.print(f"[bold]{name}[/] ({info['description']})")

        def _download(r: str = repo) -> str:
            return snapshot_download(r)

        try:
            download_with_progress(
                repo,
                _download,
                fallback_size_gb=info["size_gb"],
            )
            console.print(f"[green]✓ {name} downloaded[/]\n")
        except Exception as e:
            console.print(f"[red]✗ {name} failed: {e}[/]\n")
            raise typer.Exit(1)

    console.print("[green]All configured models are ready![/]")


@models_app.command("download")
def models_download(
    ctx: typer.Context,
    model: Annotated[str | None, typer.Argument(help="Model name to download")] = None,
) -> None:
    """Download a model.

    Examples:
        voxtype models download whisper-large-v3-turbo
        voxtype models download vyvotts-4bit
    """
    if model is None:
        import click
        click.echo(ctx.get_help())
        console.print("\n[bold]Available models:[/]")
        for name in _get_model_registry():
            console.print(f"  {name}")
        raise typer.Exit(0)

    if model not in _get_model_registry():
        console.print(f"[red]Unknown model: {model}[/]")
        console.print("[dim]Run 'voxtype models list' to see available models[/]")
        raise typer.Exit(1)

    info = _get_model_registry()[model]
    repo = info["repo"]

    from huggingface_hub import snapshot_download

    from voxtype.utils.hf_download import download_with_progress, is_repo_cached

    check_file = info.get("check_file", "config.json")
    if is_repo_cached(repo, check_file):
        console.print(f"[green]Model '{model}' is already cached[/]")
        raise typer.Exit(0)

    console.print(f"[bold]Downloading {model}...[/]")

    try:
        download_with_progress(
            repo,
            lambda: snapshot_download(repo),
            fallback_size_gb=info["size_gb"],
        )
        console.print(f"[green]Model '{model}' downloaded successfully[/]")
    except Exception as e:
        console.print(f"[red]Download failed: {e}[/]")
        raise typer.Exit(1)


@models_app.command("clear")
def models_clear(
    ctx: typer.Context,
    model: Annotated[str | None, typer.Argument(help="Model name to clear (or 'all')")] = None,
) -> None:
    """Clear cached model(s).

    Examples:
        voxtype models clear vyvotts-4bit
        voxtype models clear all
    """
    import shutil

    if model is None:
        import click
        click.echo(ctx.get_help())
        raise typer.Exit(0)

    from voxtype.utils.hf_download import get_hf_cache_dir

    if model == "all":
        if not typer.confirm("Clear ALL cached models?"):
            raise typer.Abort()

        cleared = 0
        for name, info in _get_model_registry().items():
            cache_dir = get_hf_cache_dir(info["repo"])
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
                console.print(f"  Cleared {name}")
                cleared += 1

        if cleared == 0:
            console.print("[yellow]No cached models found[/]")
        else:
            console.print(f"[green]Cleared {cleared} model(s)[/]")
        return

    if model not in _get_model_registry():
        console.print(f"[red]Unknown model: {model}[/]")
        console.print("[dim]Run 'voxtype models list' to see available models[/]")
        raise typer.Exit(1)

    info = _get_model_registry()[model]
    cache_dir = get_hf_cache_dir(info["repo"])

    if not cache_dir.exists():
        console.print(f"[yellow]Model '{model}' is not cached[/]")
        raise typer.Exit(0)

    shutil.rmtree(cache_dir)
    console.print(f"[green]Cleared '{model}'[/]")


# =============================================================================
# Tray commands
# =============================================================================


@tray_app.command("start")
def tray_start(
    foreground: Annotated[
        bool,
        typer.Option("--foreground", "-f", help="Run in foreground (for debugging)"),
    ] = False,
) -> None:
    """Start the VoxType system tray application.

    Shows an icon in the system tray/menu bar with controls for:
    - Start/Stop listening
    - Mute/Unmute
    - Target selection
    - Settings

    By default runs in background. Use --foreground for debugging.

    Example:
        voxtype tray start              # Background (daemon mode)
        voxtype tray start --foreground # Foreground (debug mode)
    """
    from voxtype.tray.lifecycle import get_tray_status, start_tray

    # Check if already running
    status = get_tray_status()
    if status.running:
        console.print(f"[yellow]Tray already running[/] (PID: {status.pid})")
        raise typer.Exit(1)

    if foreground:
        console.print("[dim]Starting VoxType tray (foreground)...[/]")
        console.print("[dim]Right-click the icon for menu. Ctrl+C to quit.[/]")

        # Connect to daemon if running
        from voxtype.daemon import get_daemon_status

        daemon_status = get_daemon_status()
        if daemon_status.running:
            console.print(f"[green]Connected to daemon[/] (PID: {daemon_status.pid})")
        else:
            console.print("[yellow]Daemon not running.[/] Start with: voxtype daemon start")

        result = start_tray(foreground=True)
        raise typer.Exit(result)
    else:
        # Background mode
        result = start_tray(foreground=False)
        if result == 0:
            import time

            time.sleep(0.3)
            status = get_tray_status()
            if status.running:
                console.print(f"[green]Tray started[/] (PID: {status.pid})")
            else:
                console.print("[red]Tray failed to start[/]")
                raise typer.Exit(1)
        else:
            console.print("[red]Tray failed to start[/]")
            raise typer.Exit(1)


@tray_app.command("stop")
def tray_stop() -> None:
    """Stop the VoxType system tray application.

    Example:
        voxtype tray stop
    """
    from voxtype.tray.lifecycle import get_tray_status, stop_tray

    status = get_tray_status()
    if not status.running:
        console.print("[yellow]Tray is not running[/]")
        raise typer.Exit(1)

    console.print(f"[dim]Stopping tray (PID: {status.pid})...[/]")
    result = stop_tray()

    if result == 0:
        console.print("[green]Tray stopped[/]")
    else:
        console.print("[red]Failed to stop tray[/]")
        raise typer.Exit(1)


@tray_app.command("status")
def tray_status() -> None:
    """Show VoxType tray status.

    Example:
        voxtype tray status
    """
    from voxtype.tray.lifecycle import get_tray_status

    status = get_tray_status()

    if status.running:
        console.print(f"[green]Tray running[/] (PID: {status.pid})")
    else:
        console.print("[dim]Tray not running[/]")


def _check_python_environment() -> None:
    """Check if running in the correct Python environment."""
    import os
    import sys

    # Expected Python version for uv tool installation
    expected_major = 3
    expected_minor = 11

    major, minor = sys.version_info[:2]

    # If running with wrong Python version, likely a PATH/shim issue
    if major != expected_major or minor != expected_minor:
        # Check if this looks like a pyenv shim issue
        executable = sys.executable
        is_pyenv_shim = ".pyenv" in executable
        is_uv_run = "UV_" in "".join(os.environ.keys()) or ".venv" in executable

        if is_pyenv_shim or is_uv_run:
            from rich.console import Console
            from rich.panel import Panel

            console = Console(
                stderr=True,
                force_terminal=None,
                force_interactive=None,
                legacy_windows=False,
                safe_box=True,
            )

            if is_pyenv_shim:
                msg = (
                    f"[yellow]⚠ voxtype is running with Python {major}.{minor} "
                    "via pyenv shim[/]\n\n"
                    f"voxtype was installed with Python {expected_major}.{expected_minor} "
                    "but pyenv is intercepting the command.\n\n"
                    "[bold]Quick fix:[/]\n"
                    "  [cyan]~/.local/bin/voxtype[/]  (use full path)\n\n"
                    "[bold]Permanent fix:[/]\n"
                    "  Move [cyan]~/.local/bin[/] AFTER pyenv init in your shell config,\n"
                    "  so uv tools take precedence over pyenv shims.\n\n"
                    "[dim]This is a PATH ordering issue, not a voxtype bug.[/]"
                )
            else:
                msg = (
                    f"[yellow]⚠ voxtype is running with Python {major}.{minor}[/]\n\n"
                    f"voxtype was installed with Python {expected_major}.{expected_minor}.\n"
                    "It looks like [cyan]uv run[/] is being used instead of the installed binary.\n\n"
                    "[bold]Fix:[/]\n"
                    "  Remove any [cyan]voxtype[/] alias from your shell config,\n"
                    "  or use [cyan]~/.local/bin/voxtype[/] directly."
                )

            console.print(Panel(msg, title="Python Environment Issue", border_style="yellow", expand=False))


def main() -> None:
    """Entry point for the CLI."""
    _check_python_environment()
    _ensure_plugins_registered()
    try:
        app()
    except ConfigError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
