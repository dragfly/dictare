"""CLI interface for voxtype."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from voxtype import __version__
from voxtype.config import (
    create_default_config,
    get_config_path,
    get_config_value,
    list_config_keys,
    load_config,
    set_config_value,
)

app = typer.Typer(
    name="voxtype",
    help="Voice-to-text for your terminal",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()

def _setup_cuda_library_path() -> None:
    """Set up CUDA libraries by preloading them before ctranslate2."""
    import ctypes
    import os

    # Find nvidia packages in site-packages
    for path in sys.path:
        nvidia_path = Path(path) / "nvidia"
        if nvidia_path.exists():
            # Preload cudnn and cublas libraries
            lib_files = [
                ("cudnn", "libcudnn.so.9"),
                ("cudnn", "libcudnn_ops.so.9"),
                ("cudnn", "libcudnn_cnn.so.9"),
                ("cublas", "libcublas.so.12"),
                ("cublas", "libcublasLt.so.12"),
            ]
            for subdir, libname in lib_files:
                lib_path = nvidia_path / subdir / "lib" / libname
                if lib_path.exists():
                    try:
                        ctypes.CDLL(str(lib_path), mode=ctypes.RTLD_GLOBAL)
                    except OSError:
                        pass  # Library already loaded or not needed

            # Also set LD_LIBRARY_PATH for any remaining libs
            lib_paths = []
            for subdir in ["cudnn", "cublas", "cuda_runtime"]:
                lib_dir = nvidia_path / subdir / "lib"
                if lib_dir.exists():
                    lib_paths.append(str(lib_dir))

            if lib_paths:
                current = os.environ.get("LD_LIBRARY_PATH", "")
                new_paths = ":".join(lib_paths)
                if current:
                    os.environ["LD_LIBRARY_PATH"] = f"{new_paths}:{current}"
                else:
                    os.environ["LD_LIBRARY_PATH"] = new_paths
            break

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
    import platform

    # If cpu_only flag is set, force CPU and skip detection
    if cpu_only:
        config.stt.device = "cpu"
        config.stt.compute_type = "int8"
        return

    # Only auto-detect if device is "auto"
    if config.stt.device != "auto":
        return

    # Default to CPU if no acceleration found
    config.stt.device = "cpu"

    if sys.platform == "darwin" and platform.machine() == "arm64":
        # Apple Silicon: try MLX
        try:
            console.print("[dim]Loading MLX (first run may take ~30s)...[/]")
            import mlx_whisper  # noqa: F401
            config.stt.backend = "mlx-whisper"
        except ImportError:
            pass  # mlx-whisper not installed, use CPU
    elif sys.platform == "linux":
        # Linux: try CUDA GPU via ctranslate2 (faster-whisper dependency)
        try:
            import ctranslate2
            cuda_device_count = ctranslate2.get_cuda_device_count()
            if cuda_device_count > 0:
                config.stt.device = "cuda"
                config.stt.compute_type = "float16"
                console.print(f"[dim]CUDA GPU detected ({cuda_device_count} device(s)), using GPU acceleration[/]")
                _setup_cuda_library_path()
        except (ImportError, RuntimeError, AttributeError):
            pass  # ctranslate2 not installed or no CUDA, using CPU

def _apply_cli_overrides(
    config,
    *,
    model: str | None,
    hotkey: str | None,
    language: str | None,
    auto_enter: bool | None,
    output: str | None,
    max_duration: int | None,
    verbose: bool | None,
    commands: bool | None,
    typing_delay: int | None,
    ollama_model: str | None,
    silence_ms: int | None,
    wake_word: str | None,
    initial_mode: str | None,
    debug: bool | None,
    log_file: str | None,
    audio_feedback: bool | None,
    hw_accel: bool | None,
) -> None:
    """Apply CLI options to config.

    Only overrides if value is explicitly provided (not None for optional, not default for bool).
    """
    if model:
        config.stt.model_size = model
    if hotkey:
        config.hotkey.key = hotkey
    if language:
        config.stt.language = language
    if auto_enter is not None:
        config.output.auto_enter = auto_enter
    if output:
        config.output.method = output
    if max_duration:
        config.audio.max_duration = max_duration
    if verbose is not None:
        config.verbose = verbose
    if commands is not None:
        config.command.enabled = commands
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
    if debug is not None:
        config.logging.debug = debug
    if log_file:
        config.logging.log_file = log_file
    if audio_feedback is not None:
        config.audio.audio_feedback = audio_feedback
    if hw_accel is not None:
        config.stt.hw_accel = hw_accel

def _format_status_panel(config, agents: list[str] | None = None) -> Panel:
    """Create the status panel for the Ready message."""
    # Device string - check what will ACTUALLY be used
    if config.stt.device == "cuda":
        # Check if cuDNN is actually available
        from voxtype.cuda_setup import _find_cudnn_path
        if _find_cudnn_path():
            device_str = "[magenta]GPU (CUDA)[/]"
        else:
            device_str = "CPU [dim](GPU detected, cuDNN missing)[/]"
    elif not config.stt.hw_accel:
        device_str = "CPU"
    else:
        device_str = "CPU"  # Auto-detect didn't find acceleration

    # Output mode
    if agents:
        output_str = f"[cyan]agents[/] ({', '.join(agents)})"
    elif config.output.method == "clipboard":
        output_str = "[yellow]clipboard[/] (Ctrl+V to paste)"
    elif config.output.method == "agent":
        output_str = "[cyan]agent[/] (single)"
    else:
        output_str = config.output.method

    mode_str = "[cyan]transcription[/] (fast)" if config.command.mode == "transcription" else "[yellow]command[/] (LLM)"
    wake_str = f"Wake word: [cyan]{config.command.wake_word}[/]\n" if config.command.wake_word else ""

    # Format the hotkey nicely
    hotkey = config.hotkey.key
    if hotkey in ("KEY_LEFTMETA", "KEY_RIGHTMETA"):
        hotkey_display = "⌘ (Command)" if sys.platform == "darwin" else "Super/Meta"
    elif hotkey == "KEY_SCROLLLOCK":
        hotkey_display = "Scroll Lock"
    else:
        hotkey_display = hotkey.replace("KEY_", "")

    return Panel(
        f"[bold green]voxtype[/] v{__version__}\n\n"
        f"{wake_str}"
        f"Mode: {mode_str}\n"
        f"STT: [cyan]{config.stt.model_size}[/] on {device_str}\n"
        f"Language: [cyan]{config.stt.language}[/]\n"
        f"Output: {output_str}\n\n"
        f"[dim][cyan]{hotkey_display}[/] tap: toggle listening | double-tap: switch mode[/]\n"
        f"Press [bold]Ctrl+C[/] to exit",
        title="Ready",
        border_style="green",
    )

def _create_logger(config):
    """Create JSONL logger if log file is specified in config."""
    if not config.logging.log_file:
        return None

    from voxtype.logging.jsonl import JSONLLogger

    log_params = {
        "input_mode": "vad" if config.audio.vad else "push_to_talk",
        "trigger_phrase": config.command.wake_word,
        "debug": config.logging.debug,
        "silence_ms": config.audio.silence_ms,
        "stt_model": config.stt.model_size,
        "stt_language": config.stt.language,
        "output_method": config.output.method,
    }
    return JSONLLogger(Path(config.logging.log_file), __version__, params=log_params)

@app.callback()
def main_callback(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-V", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """voxtype: Voice-to-text for your terminal."""
    pass

@app.command()
def run(
    # Config file
    config_file: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    # STT options
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Whisper model (tiny/base/small/medium/large-v3/large-v3-turbo)"),
    ] = None,
    language: Annotated[
        Optional[str],
        typer.Option("--language", "-l", help="Language code or 'auto'"),
    ] = None,
    hw_accel: Annotated[
        Optional[bool],
        typer.Option("--hw-accel", help="Hardware acceleration (true=auto-detect, false=CPU only)"),
    ] = None,
    # Input options
    silence_ms: Annotated[
        Optional[int],
        typer.Option("--silence-ms", "-s", help="VAD silence duration to end speech (ms)"),
    ] = None,
    hotkey: Annotated[
        Optional[str],
        typer.Option("--hotkey", "-k", help="Toggle listening key (default: SCROLLLOCK)"),
    ] = None,
    max_duration: Annotated[
        Optional[int],
        typer.Option("--max-duration", "-d", help="Max recording duration in seconds"),
    ] = None,
    # Output options
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output method: keyboard, clipboard, or agent"),
    ] = None,
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", "-D", help="Directory for agent files (<agent>.voxtype)"),
    ] = None,
    agents: Annotated[
        Optional[str],
        typer.Option("--agents", "-A", help="Agent IDs comma-separated (e.g., 'claude,pippo')"),
    ] = None,
    typing_delay: Annotated[
        Optional[int],
        typer.Option("--typing-delay", help="Delay between keystrokes in ms"),
    ] = None,
    auto_enter: Annotated[
        Optional[bool],
        typer.Option("--auto-enter", help="Auto-submit after typing (true/false)"),
    ] = None,
    # Command options
    wake_word: Annotated[
        Optional[str],
        typer.Option("--wake-word", "-w", help="Wake word to activate (e.g., 'hey joshua')"),
    ] = None,
    initial_mode: Annotated[
        Optional[str],
        typer.Option("--initial-mode", "-M", help="Starting mode: transcription or command"),
    ] = None,
    commands: Annotated[
        Optional[bool],
        typer.Option("--commands", help="Enable voice commands (true/false)"),
    ] = None,
    ollama_model: Annotated[
        Optional[str],
        typer.Option("--ollama-model", "-O", help="Ollama model for command processing"),
    ] = None,
    # Controller
    controller: Annotated[
        Optional[str],
        typer.Option("--controller", help="Controller device name for agent switching"),
    ] = None,
    # Debug/logging options
    verbose: Annotated[
        Optional[bool],
        typer.Option("--verbose", "-v", help="Verbose output (true/false)"),
    ] = None,
    debug: Annotated[
        Optional[bool],
        typer.Option("--debug", help="Debug mode (true/false)"),
    ] = None,
    log_file: Annotated[
        Optional[str],
        typer.Option("--log-file", "-L", help="JSONL log file path"),
    ] = None,
    audio_feedback: Annotated[
        Optional[bool],
        typer.Option("--audio-feedback", help="Play beep sounds (true/false)"),
    ] = None,
) -> None:
    """Start voxtype voice-to-text.

    Uses Voice Activity Detection (VAD) to automatically detect when you speak.
    Tap the hotkey to toggle listening on/off, double-tap to switch mode.
    """
    config = load_config(config_file)

    # Apply CLI overrides first (so hw_accel is set before auto-detect)
    _apply_cli_overrides(
        config,
        model=model,
        hotkey=hotkey,
        language=language,
        auto_enter=auto_enter,
        output=output,
        max_duration=max_duration,
        verbose=verbose,
        commands=commands,
        typing_delay=typing_delay,
        ollama_model=ollama_model,
        silence_ms=silence_ms,
        wake_word=wake_word,
        initial_mode=initial_mode,
        debug=debug,
        log_file=log_file,
        audio_feedback=audio_feedback,
        hw_accel=hw_accel,
    )

    # Auto-detect hardware acceleration (unless hw_accel=false)
    _auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

    # Auto-detect hotkey based on platform (if using default)
    if config.hotkey.key == "KEY_SCROLLLOCK" and sys.platform == "darwin":
        # macOS doesn't have ScrollLock, use Right Command instead
        config.hotkey.key = "KEY_RIGHTMETA"

    # Lazy import to speed up CLI
    from voxtype.core.app import VoxtypeApp

    # Create JSONL logger if requested
    logger = _create_logger(config)

    # Handle agent mode - parse comma-separated string
    agent_list = [a.strip() for a in agents.split(",")] if agents else None
    output_dir_str = str(output_dir) if output_dir else None
    controller_device = controller or config.controller.device

    # If agents specified but no output_dir, default to current directory
    if agent_list and not output_dir_str:
        output_dir_str = "."

    # If output_dir specified but no agents, default to ["voxtype"]
    if output_dir_str and not agent_list:
        agent_list = ["voxtype"]

    voxtypeapp = VoxtypeApp(
        config,
        logger=logger,
        output_dir=output_dir_str,
        agents=agent_list,
        controller_device=controller_device,
    )

    console.print(_format_status_panel(config, agent_list))

    try:
        voxtypeapp.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/]")
        voxtypeapp.stop()
    finally:
        if logger:
            logger.close()

@app.command()
def check() -> None:
    """Check system dependencies and configuration."""
    from voxtype.utils.platform import check_dependencies

    console.print(Panel("[bold]Checking dependencies...[/]", border_style="blue"))
    console.print()

    results = check_dependencies()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    all_ok = True
    missing_with_hints = []
    optional_with_hints = []

    for result in results:
        if result.available:
            status = "[green]OK[/]"
        elif result.required:
            status = "[red]MISSING[/]"
            all_ok = False
            if result.install_hint:
                missing_with_hints.append(result)
        else:
            status = "[yellow]OPTIONAL[/]"
            if result.install_hint:
                optional_with_hints.append(result)

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
            # Deduplicate hints (e.g., mlx-whisper and pynput both suggest same install)
            seen_hints: set[str] = set()
            for result in missing_with_hints:
                if result.install_hint and result.install_hint not in seen_hints:
                    seen_hints.add(result.install_hint)
                    # Escape Rich markup in hint (e.g., [mlx,macos] would be interpreted as style)
                    hint = result.install_hint.replace("[", r"\[")
                    console.print(f"  [cyan]{hint}[/]")
        raise typer.Exit(1)

    # Check for at least one text injection method (Linux only)
    # macOS uses osascript/pbcopy which are built-in
    if sys.platform == "linux":
        injection_methods = ["ydotool", "wtype", "xdotool"]
        has_injection = any(r.available for r in results if r.name in injection_methods)
        clipboard_available = any(r.available for r in results if r.name == "Clipboard")

        if not has_injection:
            if clipboard_available:
                console.print(
                    "\n[yellow]Warning:[/] No auto-typing tool available. "
                    "Text will be copied to clipboard instead."
                )
            else:
                console.print(
                    "\n[red]Warning:[/] No text injection method available. "
                    "Install ydotool, wtype, or xdotool."
                )

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
config_app = typer.Typer(help="Manage configuration")
app.add_typer(config_app, name="config")

@config_app.callback(invoke_without_command=True)
def config_default(ctx: typer.Context) -> None:
    """Show all configuration (default when no subcommand given)."""
    if ctx.invoked_subcommand is None:
        _show_config_list()

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
    console.print()

    if config_path.exists():
        console.print(f"[dim]Config file: {config_path}[/]")
    else:
        console.print(f"[dim]Config file: {config_path} (not created, using defaults)[/]")
        console.print("[dim]Run 'voxtype init' to create config file[/]")

@config_app.command("get")
def config_get(
    key: Annotated[str, typer.Argument(help="Config key (e.g., stt.model_size)")],
) -> None:
    """Get a configuration value."""
    try:
        value = get_config_value(key)
        console.print(value)
    except KeyError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(1)

@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key (e.g., stt.model_size)")],
    value: Annotated[str, typer.Argument(help="Value to set")],
) -> None:
    """Set a configuration value."""
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

@app.command()
def speak(
    text: Annotated[
        str,
        typer.Argument(help="Text to speak"),
    ],
    language: Annotated[
        str,
        typer.Option("--language", "-l", help="Language code (it, en, de, etc.)"),
    ] = "it",
    speed: Annotated[
        int,
        typer.Option("--speed", "-s", help="Speech speed in words per minute"),
    ] = 160,
) -> None:
    """Speak text using text-to-speech.

    Example: voxtype speak "Ciao Paola!"
    """
    from voxtype.tts.espeak import EspeakTTS

    tts = EspeakTTS(language=language, speed=speed)

    if not tts.is_available():
        console.print("[red]espeak not found. Install with:[/]")
        console.print("  sudo apt install espeak-ng")
        raise typer.Exit(1)

    console.print(f"[dim]Speaking: {text[:50]}{'...' if len(text) > 50 else ''}[/]")
    tts.speak(text)

@app.command()
def transcribe(
    config_file: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Whisper model size (tiny/base/small/medium/large-v3/large-v3-turbo)"),
    ] = None,
    language: Annotated[
        Optional[str],
        typer.Option("--language", "-l", help="Language code or 'auto'"),
    ] = None,
    hw_accel: Annotated[
        Optional[bool],
        typer.Option("--hw-accel", help="Hardware acceleration (true=auto-detect, false=CPU only)"),
    ] = None,
    silence_ms: Annotated[
        int,
        typer.Option("--silence-ms", "-s", help="Silence duration to end recording (ms)"),
    ] = 1200,
    max_duration: Annotated[
        int,
        typer.Option("--max-duration", "-d", help="Max recording duration in seconds"),
    ] = 60,
    output_file: Annotated[
        Optional[Path],
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
    if hw_accel is not None:
        config.stt.hw_accel = hw_accel

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

        # Create STT engine
        if getattr(config.stt, "backend", "faster-whisper") == "mlx-whisper":
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

def main() -> None:
    """Entry point for the CLI."""
    app()

if __name__ == "__main__":
    main()
