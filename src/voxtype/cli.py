"""CLI interface for voxtype."""

from __future__ import annotations

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
    """Auto-detect hardware acceleration (MLX on macOS, CUDA on Linux).

    Args:
        config: The configuration object to update
        cpu_only: If True, skip detection and force CPU
    """
    from voxtype.utils.hardware import (
        is_cuda_available,
        is_mlx_available,
        is_virtualized_macos,
        setup_cuda_library_path,
    )

    # If cpu_only flag is set, force CPU and skip detection
    if cpu_only:
        config.stt.device = "cpu"
        config.stt.compute_type = "int8"
        return

    # Check if running in a VM on macOS - disable MLX if so
    if is_virtualized_macos():
        config.stt.device = "cpu"
        config.stt.compute_type = "int8"
        config.stt.hw_accel = False
        # Inform user about VM detection (will be shown before "Ready" panel)
        console.print("[yellow]⚠ Virtualized macOS detected - hardware acceleration disabled[/]")
        console.print("[dim]MLX Metal kernels are not compatible with virtualized environments.[/]")
        return

    # Only auto-detect if device is "auto"
    if config.stt.device != "auto":
        return

    # Default to CPU if no acceleration found
    config.stt.device = "cpu"

    if is_mlx_available():
        # Apple Silicon with MLX: will be used automatically if hw_accel=true
        pass
    elif is_cuda_available():
        config.stt.device = "cuda"
        config.stt.compute_type = "float16"
        setup_cuda_library_path()

def _apply_cli_overrides(
    config,
    *,
    model: str | None,
    hotkey: str | None,
    language: str | None,
    auto_enter: bool,
    max_duration: int | None,
    verbose: bool | None,
    no_commands: bool,
    typing_delay: int | None,
    ollama_model: str | None,
    silence_ms: int | None,
    wake_word: str | None,
    initial_mode: str | None,
    log_file: str | None,
    no_audio_feedback: bool,
    no_hw_accel: bool,
    webhook: str | None,
    sse: bool,
    sse_port: int | None,
    translate: bool = False,
) -> None:
    """Apply CLI options to config.

    Boolean flags use negative form (--no-X) for features that are ON by default.
    """
    if model:
        config.stt.model_size = model
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
    if no_commands:
        config.command.enabled = False
    if typing_delay is not None:
        config.output.typing_delay_ms = typing_delay
    if ollama_model:
        config.command.ollama_model = ollama_model
    if silence_ms is not None:
        config.audio.silence_ms = silence_ms
    if wake_word is not None:
        config.command.wake_word = wake_word
    if initial_mode:
        config.command.mode = initial_mode
    if log_file:
        config.logging.log_file = log_file
    if no_audio_feedback:
        config.audio.audio_feedback = False
    if no_hw_accel:
        config.stt.hw_accel = False
    if webhook:
        config.webhook.url = webhook
    if sse:
        config.sse.enabled = True
    if sse_port is not None:
        config.sse.port = sse_port
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
        "trigger_phrase": config.command.wake_word,
        "log_level": level.name,
        "silence_ms": config.audio.silence_ms,
        "stt_model": config.stt.model_size,
        "stt_language": config.stt.language,
        "output_method": config.output.method,
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
        typer.Option("--max-duration", "-d", help="Max recording duration in seconds"),
    ] = None,
    # Output options
    agents: Annotated[
        str | None,
        typer.Option("--agents", "-A", help="Agent IDs comma-separated (e.g., 'claude,pippo')"),
    ] = None,
    typing_delay: Annotated[
        int | None,
        typer.Option("--typing-delay", help="Delay between keystrokes in ms"),
    ] = None,
    auto_enter: Annotated[
        bool,
        typer.Option("--auto-enter", help="Press Enter after typing to submit"),
    ] = False,
    # Command options
    wake_word: Annotated[
        str | None,
        typer.Option("--wake-word", "-w", help="Wake word to activate (e.g., 'hey joshua')"),
    ] = None,
    initial_mode: Annotated[
        str | None,
        typer.Option("--initial-mode", "-M", help="Starting mode: transcription or command"),
    ] = None,
    no_commands: Annotated[
        bool,
        typer.Option("--no-commands", help="Disable voice commands"),
    ] = False,
    ollama_model: Annotated[
        str | None,
        typer.Option("--ollama-model", "-O", help="Ollama model for command processing"),
    ] = None,
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
    # Webhook/SSE options
    webhook: Annotated[
        str | None,
        typer.Option("--webhook", "-W", help="Webhook URL to POST transcriptions to"),
    ] = None,
    sse: Annotated[
        bool,
        typer.Option("--sse", help="Enable SSE server for streaming events"),
    ] = False,
    sse_port: Annotated[
        int | None,
        typer.Option("--sse-port", help="Port for SSE server (default: 8765)"),
    ] = None,
) -> None:
    """Start listening for voice input.

    Uses Voice Activity Detection (VAD) to automatically detect when you speak.
    Tap the hotkey to toggle listening on/off, double-tap to switch mode.

    Example with agent:

        # Terminal 1: Start the agent
        voxtype agent macinanumeri -- claude -c

        # Terminal 2: Listen and send to agent
        voxtype listen --agents macinanumeri
    """
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
        no_commands=no_commands,
        typing_delay=typing_delay,
        ollama_model=ollama_model,
        silence_ms=silence_ms,
        wake_word=wake_word,
        initial_mode=initial_mode,
        log_file=log_file,
        no_audio_feedback=no_audio_feedback,
        no_hw_accel=no_hw_accel,
        webhook=webhook,
        sse=sse,
        sse_port=sse_port,
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

    # Lazy import to speed up CLI
    from voxtype.core.app import VoxtypeApp

    # Handle agent mode - parse comma-separated string
    agent_list = [a.strip() for a in agents.split(",")] if agents else None

    # Create JSONL logger (always enabled by default)
    logger = _create_logger(config, agents=agent_list)

    voxtypeapp = VoxtypeApp(
        config,
        logger=logger,
        agents=agent_list,
        realtime=realtime,
    )

    # Create live status panel (will be started after loading)
    log_path_str = str(logger.log_path) if logger else None
    status_panel = LiveStatusPanel(config, console, agents=agent_list, log_path=log_path_str)

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
                if _resource_tracker._pid:
                    os.kill(_resource_tracker._pid, sig.SIGKILL)
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
                if _resource_tracker._pid:
                    os.kill(_resource_tracker._pid, sig.SIGKILL)
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
        console.print(f"[yellow]Some dependencies still missing (run 'voxtype dependencies check' for details)[/]")
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
    key: Annotated[str | None, typer.Argument(help="Config key (e.g., stt.model_size)")] = None,
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
    key: Annotated[str | None, typer.Argument(help="Config key (e.g., stt.model_size)")] = None,
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
        try:
            client = DaemonClient()
            response = client.get_status()

            if hasattr(response, "uptime_seconds"):
                uptime = response.uptime_seconds
                if uptime < 60:
                    uptime_str = f"{uptime:.0f}s"
                elif uptime < 3600:
                    uptime_str = f"{uptime / 60:.1f}m"
                else:
                    uptime_str = f"{uptime / 3600:.1f}h"
                console.print(f"  Uptime: {uptime_str}")
                console.print(f"  Requests served: {response.requests_served}")
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
            config.stt.model_size = model
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
            config.stt.model_size,
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
            config.stt.model_size = model
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
            config.stt.model_size,
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

    socket_path = "/tmp/voxtype.sock"

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
) -> None:
    """Run a command with voxtype voice input via OpenVIP.

    Listens on a Unix socket for OpenVIP messages from 'voxtype listen --agents'.

    Example:

        # Terminal 1: Start the agent wrapper
        voxtype agent claude -- claude

        # Terminal 2: Send voice input via OpenVIP
        voxtype listen --agents claude
    """
    # Show help if no agent_id
    if agent_id is None:
        import click
        click.echo(ctx.get_help())
        raise typer.Exit(0)

    from voxtype.agent import run_agent

    # Get command after -- (filter out the -- itself if present)
    command = [arg for arg in ctx.args if arg != "--"]
    if not command:
        console.print("[red]Error: No command specified[/]")
        console.print()
        console.print("[dim]Usage: voxtype agent AGENT_ID -- COMMAND...[/]")
        console.print("[dim]Example: voxtype agent claude -- claude[/]")
        raise typer.Exit(1)

    exit_code = run_agent(agent_id, command, quiet=quiet)
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
            ts = entry.get("ts", "")
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
                version = entry.get("version", "?")
                model = entry.get("stt_model", "?")
                extra = f"v{version} model={model}"
            elif event == "session_end":
                extra = ""
            elif event == "transcription":
                chars = entry.get("chars", 0)
                words = entry.get("words", 0)
                duration = entry.get("duration_ms", 0)
                extra = f"{words}w {chars}c {duration:.0f}ms"
            elif event == "transcription_text":
                text = entry.get("text", "")[:60]
                extra = f'"{text}"' + ("..." if len(entry.get("text", "")) > 60 else "")
            elif event == "injection":
                chars = entry.get("chars", 0)
                method = entry.get("method", "?")
                success = "ok" if entry.get("success") else "fail"
                extra = f"{chars}c via {method} [{success}]"
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

def _get_configured_models(config=None) -> set[str]:
    """Get model names that are configured to be used.

    Returns:
        Set of model registry keys that are currently configured.
    """
    if config is None:
        config = load_config()

    configured = set()
    registry = _get_model_registry()

    # STT model: map config value to registry key
    # e.g., "large-v3-turbo" -> "whisper-large-v3-turbo"
    stt_model = config.stt.model_size
    stt_key = f"whisper-{stt_model}"
    if stt_key in registry:
        configured.add(stt_key)

    # TTS model: find model by engine
    # e.g., "qwen3" -> "vyvotts-4bit", "outetts" -> "outetts"
    tts_engine = config.tts.engine
    if tts_engine in ("qwen3", "outetts"):
        for name, info in registry.items():
            if info.get("engine") == tts_engine:
                # Pick first (default) model for that engine
                configured.add(name)
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

    for name in configured:
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
        for name in missing:
            console.print(f"  [cyan]voxtype models download {name}[/]")
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
    table.add_column("Status", justify="center")
    table.add_column("Size", justify="right")
    table.add_column("Description")

    for name, info in _get_model_registry().items():
        repo = info["repo"]
        model_type = info["type"].upper()
        is_configured = name in configured

        # Check if cached
        check_file = info.get("check_file", "config.json")
        cached = is_repo_cached(repo, check_file)

        # Determine colors based on configured + cached state
        if is_configured:
            if cached:
                # Configured and cached = green
                name_style = "[green]"
                status = "[green]cached[/]"
            else:
                # Configured but not cached = red
                name_style = "[red]"
                status = "[red]MISSING[/]"
        else:
            # Not configured = normal/dim
            name_style = "[dim]"
            status = "[dim]cached[/]" if cached else "[dim]—[/]"

        # Size
        if cached:
            cache_size = get_cache_size(repo)
            size_str = _format_size(cache_size) if cache_size > 0 else f"~{info['size_gb']:.1f} GB"
        else:
            size_str = f"~{info['size_gb']:.1f} GB"

        table.add_row(
            f"{name_style}{name}[/]",
            model_type,
            status,
            size_str,
            info["description"],
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
    console.print("[dim]Resolve:  voxtype models resolve[/]")
    console.print("[dim]Download: voxtype models download <model>[/]")
    console.print("[dim]Clear:    voxtype models clear <model>[/]")

@models_app.command("resolve")
def models_resolve() -> None:
    """Download all configured models that are missing.

    Automatically downloads models needed for your current configuration.

    Example:
        voxtype models resolve
    """
    from voxtype.utils.hf_download import download_with_progress, is_repo_cached
    from huggingface_hub import snapshot_download

    config = load_config()
    configured = _get_configured_models(config)
    registry = _get_model_registry()

    # Find missing models
    missing = []
    for name in configured:
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
        repo = info["repo"]

        console.print(f"[bold]{name}[/] ({info['description']})")

        try:
            download_with_progress(
                repo,
                lambda r=repo: snapshot_download(r),
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

    from voxtype.utils.hf_download import download_with_progress, is_repo_cached
    from huggingface_hub import snapshot_download

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
    try:
        app()
    except ConfigError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
