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
    from voxtype.utils.hardware import is_cuda_available, is_mlx_available, setup_cuda_library_path

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
    output: str | None,
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
    if output:
        config.output.method = output
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


def _format_status_panel(config, agents: list[str] | None = None) -> Panel:
    """Create the status panel for the Ready message."""
    from voxtype.utils.hardware import is_mlx_available

    # Device string - check what will ACTUALLY be used
    device_str = "CPU"

    if not config.stt.hw_accel:
        device_str = "CPU"
    elif config.stt.device == "cuda":
        # Check if cuDNN is actually available
        from voxtype.cuda_setup import _find_cudnn_path
        if _find_cudnn_path():
            device_str = "[magenta]GPU (CUDA)[/]"
        else:
            device_str = "CPU [dim](GPU detected, cuDNN missing)[/]"
    elif is_mlx_available():
        device_str = "[magenta]MLX (Apple Silicon)[/]"

    # Output mode
    if agents:
        output_str = f"[cyan]agents[/] ({', '.join(agents)})"
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
        f"[dim]Hotkey: [cyan]{hotkey_display}[/] tap: toggle listening | double-tap: switch mode[/]\n"
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
        "input_mode": "vad",  # PTT mode removed in v2.2.0
        "trigger_phrase": config.command.wake_word,
        "verbose": config.verbose,
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
    no_hw_accel: Annotated[
        bool,
        typer.Option("--no-hw-accel", help="Disable hardware acceleration (force CPU)"),
    ] = False,
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
        typer.Option("--output", "-o", help="Output method: keyboard or agent"),
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
        bool,
        typer.Option("--auto-enter", help="Press Enter after typing to submit"),
    ] = False,
    # Command options
    wake_word: Annotated[
        Optional[str],
        typer.Option("--wake-word", "-w", help="Wake word to activate (e.g., 'hey joshua')"),
    ] = None,
    initial_mode: Annotated[
        Optional[str],
        typer.Option("--initial-mode", "-M", help="Starting mode: transcription or command"),
    ] = None,
    no_commands: Annotated[
        bool,
        typer.Option("--no-commands", help="Disable voice commands"),
    ] = False,
    ollama_model: Annotated[
        Optional[str],
        typer.Option("--ollama-model", "-O", help="Ollama model for command processing"),
    ] = None,
    # Debug/logging options
    verbose: Annotated[
        Optional[bool],
        typer.Option("--verbose", "-v", help="Verbose output: show device info, transcriptions, debug messages"),
    ] = None,
    log_file: Annotated[
        Optional[str],
        typer.Option("--log-file", "-L", help="JSONL log file path"),
    ] = None,
    no_audio_feedback: Annotated[
        bool,
        typer.Option("--no-audio-feedback", help="Disable beep sounds"),
    ] = False,
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
        no_commands=no_commands,
        typing_delay=typing_delay,
        ollama_model=ollama_model,
        silence_ms=silence_ms,
        wake_word=wake_word,
        initial_mode=initial_mode,
        log_file=log_file,
        no_audio_feedback=no_audio_feedback,
        no_hw_accel=no_hw_accel,
    )

    # Auto-detect hardware acceleration (unless --no-hw-accel)
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

    # output_dir only makes sense with agents
    if agent_list and not output_dir_str:
        output_dir_str = "."
    elif output_dir_str and not agent_list:
        output_dir_str = None  # Ignore output_dir without agents

    voxtypeapp = VoxtypeApp(
        config,
        logger=logger,
        output_dir=output_dir_str,
        agents=agent_list,
    )

    # Create status panel to show after loading (not before!)
    status_panel = _format_status_panel(config, agent_list)

    try:
        voxtypeapp.run(status_panel=status_panel)
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

    # Check for text injection method (Linux only)
    # macOS uses Quartz which is built-in
    if sys.platform == "linux":
        has_ydotool = any(r.available for r in results if r.name == "ydotool")
        if not has_ydotool:
            console.print(
                "\n[red]Warning:[/] ydotool not available. "
                "Install ydotool and start ydotoold daemon."
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
            console.print("[red]hidapi package not installed[/]")
            console.print("This should be installed automatically on macOS.")
            console.print("Try: [cyan]pip install hidapi[/]")
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

    table = Table(title="HID Devices", show_header=True, header_style="bold")
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
        console.print("[red]evdev not installed[/]")
        console.print("Install with: [cyan]pip install evdev[/]")
        raise typer.Exit(1)

    # Collect all devices with their info
    devices_info = []
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
    table = Table(title="Input Devices", show_header=True, header_style="bold")
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
    command: Annotated[str, typer.Argument(help="Command to send (e.g., toggle-listening)")],
) -> None:
    """Send a command to a running voxtype instance.

    Used by external tools (like Karabiner-Elements) to control voxtype.

    Available commands:
        toggle-listening, listening-on, listening-off,
        toggle-mode, project-next, project-prev,
        submit, discard, repeat

    Example:
        voxtype cmd toggle-listening
        voxtype cmd project-next
    """
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
        console.print("[dim]Start voxtype first: voxtype run[/]")
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
        console.print("[yellow]No device backends available[/]")
        console.print()
        console.print("[dim]Install dependencies:[/]")
        console.print("  macOS: [cyan]pip install hidapi[/] or [cyan]brew install --cask karabiner-elements[/]")
        console.print("  Linux: [cyan]pip install evdev[/]")
        raise typer.Exit(1)

    table = Table(title="Device Backends", show_header=True, header_style="bold")
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


def _check_python_environment() -> None:
    """Check if running in the correct Python environment."""
    import sys
    import os

    # Expected Python version for uv tool installation
    EXPECTED_MAJOR = 3
    EXPECTED_MINOR = 11

    major, minor = sys.version_info[:2]

    # If running with wrong Python version, likely a PATH/shim issue
    if major != EXPECTED_MAJOR or minor != EXPECTED_MINOR:
        # Check if this looks like a pyenv shim issue
        executable = sys.executable
        is_pyenv_shim = ".pyenv" in executable
        is_uv_run = "UV_" in "".join(os.environ.keys()) or ".venv" in executable

        if is_pyenv_shim or is_uv_run:
            from rich.console import Console
            from rich.panel import Panel

            console = Console(stderr=True)

            if is_pyenv_shim:
                msg = (
                    f"[yellow]⚠ voxtype is running with Python {major}.{minor} via pyenv shim[/]\n\n"
                    f"voxtype was installed with Python {EXPECTED_MAJOR}.{EXPECTED_MINOR} but pyenv is intercepting the command.\n\n"
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
                    f"voxtype was installed with Python {EXPECTED_MAJOR}.{EXPECTED_MINOR}.\n"
                    "It looks like [cyan]uv run[/] is being used instead of the installed binary.\n\n"
                    "[bold]Fix:[/]\n"
                    "  Remove any [cyan]voxtype[/] alias from your shell config,\n"
                    "  or use [cyan]~/.local/bin/voxtype[/] directly."
                )

            console.print(Panel(msg, title="Python Environment Issue", border_style="yellow"))
            console.print()


def main() -> None:
    """Entry point for the CLI."""
    _check_python_environment()
    app()


if __name__ == "__main__":
    main()
