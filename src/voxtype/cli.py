"""CLI interface for voxtype."""

from __future__ import annotations

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
    import sys

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
    config_file: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Whisper model size (tiny/base/small/medium/large-v3)"),
    ] = None,
    key: Annotated[
        Optional[str],
        typer.Option("--key", "-k", help="Push-to-talk key (e.g., KEY_SCROLLLOCK)"),
    ] = None,
    language: Annotated[
        Optional[str],
        typer.Option("--language", "-l", help="Language code or 'auto'"),
    ] = None,
    no_enter: Annotated[
        bool,
        typer.Option("--no-enter", help="Don't press Enter after typing/pasting"),
    ] = False,
    clipboard: Annotated[
        bool,
        typer.Option("--clipboard", "-C", help="Use clipboard instead of typing (for accented chars)"),
    ] = False,
    gpu: Annotated[
        bool,
        typer.Option("--gpu", "-g", help="Use GPU (CUDA) for faster transcription"),
    ] = False,
    mlx: Annotated[
        bool,
        typer.Option("--mlx", help="Use MLX (Apple Silicon) for faster transcription"),
    ] = False,
    max_duration: Annotated[
        Optional[int],
        typer.Option("--max-duration", "-d", help="Max recording duration in seconds (default 60)"),
    ] = None,
    vad: Annotated[
        bool,
        typer.Option("--vad/--ptt", help="VAD mode (default) or push-to-talk mode"),
    ] = True,
    silence_ms: Annotated[
        Optional[int],
        typer.Option("--silence-ms", "-s", help="VAD silence duration to end speech (default 1200)"),
    ] = None,
    wake_word: Annotated[
        Optional[str],
        typer.Option("--wake-word", "-w", help="Wake word to activate (e.g., 'Joshua')"),
    ] = None,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Debug mode: show all transcriptions but only paste with wake word"),
    ] = False,
    no_commands: Annotated[
        bool,
        typer.Option("--no-commands", help="Disable voice command processing"),
    ] = False,
    mode: Annotated[
        str,
        typer.Option("--mode", "-M", help="Mode: 'transcription' (fast, no LLM) or 'command' (LLM for commands)"),
    ] = "transcription",
    log_file: Annotated[
        Optional[Path],
        typer.Option("--log-file", "-L", help="JSONL log file for structured logging"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
    typing_delay: Annotated[
        Optional[int],
        typer.Option("--typing-delay", help="Delay between keystrokes in ms (for keyboard mode)"),
    ] = None,
    keyboard: Annotated[
        bool,
        typer.Option("--keyboard", "-K", help="Use keyboard typing instead of clipboard (may crash some apps)"),
    ] = False,
    ollama_model: Annotated[
        Optional[str],
        typer.Option("--ollama-model", "-O", help="Ollama model for command processing (default: qwen2.5:1.5b)"),
    ] = None,
) -> None:
    """Start voxtype in push-to-talk or VAD mode.

    Push-to-talk: Hold the configured key while speaking, release to transcribe.
    VAD mode: Automatically detects when you speak, no key needed.
    """
    config = load_config(config_file)

    # Auto-detect GPU acceleration
    import platform
    import sys
    if sys.platform == "darwin" and platform.machine() == "arm64":
        # Apple Silicon: try MLX
        try:
            console.print("[dim]Loading MLX (first run may take ~30s)...[/]")
            import mlx_whisper  # noqa: F401
            config.stt.backend = "mlx-whisper"
        except ImportError:
            pass  # mlx-whisper not installed, use default
    elif sys.platform == "linux":
        # Linux: try CUDA GPU via ctranslate2 (faster-whisper dependency)
        try:
            import ctranslate2
            # Check if CUDA device is available
            cuda_device_count = ctranslate2.get_cuda_device_count()
            if cuda_device_count > 0:
                config.stt.device = "cuda"
                config.stt.compute_type = "float16"
                console.print(f"[dim]CUDA GPU detected ({cuda_device_count} device(s)), using GPU acceleration[/]")
                _setup_cuda_library_path()
        except (ImportError, RuntimeError, AttributeError):
            pass  # ctranslate2 not installed or no CUDA

    # Auto-detect hotkey based on platform (if using default)
    if config.hotkey.key == "KEY_SCROLLLOCK" and sys.platform == "darwin":
        # macOS doesn't have ScrollLock, use Right Command instead
        config.hotkey.key = "KEY_RIGHTMETA"

    # Override config with CLI options
    if model:
        config.stt.model_size = model
    if key:
        config.hotkey.key = key
    if language:
        config.stt.language = language
    if no_enter:
        config.injection.auto_enter = False
    if clipboard:
        config.injection.backend = "clipboard"
    if mlx:
        config.stt.backend = "mlx-whisper"
    elif gpu:
        config.stt.device = "cuda"
        config.stt.compute_type = "float16"  # Better for GPU
        _setup_cuda_library_path()
    if max_duration:
        config.audio.max_duration = max_duration
    if verbose:
        config.verbose = verbose
    if no_commands:
        config.command.enabled = False
    if typing_delay is not None:
        config.injection.typing_delay_ms = typing_delay
    if keyboard:
        # Force keyboard mode (ydotool/wtype/xdotool on Linux, macos on macOS)
        import sys
        if sys.platform == "darwin":
            config.injection.backend = "macos"
        else:
            config.injection.backend = "ydotool"  # Will fall back to wtype/xdotool
    if ollama_model:
        config.command.ollama_model = ollama_model

    # Lazy import to speed up CLI
    from voxtype.core.app import VoxtypeApp

    # Create JSONL logger if requested
    logger = None
    if log_file:
        from voxtype.logging import JSONLLogger

        # Collect startup parameters for logging
        log_params = {
            "input_mode": "vad" if vad else "push_to_talk",
            "trigger_phrase": wake_word,
            "stt_model": config.stt.model_size,
            "stt_device": config.stt.device,
            "stt_language": config.stt.language,
            "output_mode": config.injection.backend,
            "auto_enter": config.injection.auto_enter,
            "debug": debug,
            "silence_ms": silence_ms or VoxtypeApp.DEFAULT_VAD_SILENCE_MS,
        }
        logger = JSONLLogger(log_file, __version__, params=log_params)
        console.print(f"[dim]Logging to: {log_file}[/]")

    app = VoxtypeApp(
        config,
        use_vad=vad,
        vad_silence_ms=silence_ms,
        wake_word=wake_word,
        debug=debug,
        logger=logger,
        initial_mode=mode,
    )

    output_str = "[yellow]clipboard[/] (Ctrl+V to paste)" if clipboard else "keyboard"
    mode_str = "[cyan]transcription[/] (fast)" if mode == "transcription" else "[yellow]command[/] (LLM)"
    if config.stt.backend == "mlx-whisper":
        device_str = "[magenta]GPU (MLX/Metal)[/]"
    elif config.stt.device == "cuda":
        device_str = "[magenta]GPU (CUDA)[/]"
    else:
        device_str = "CPU"
    input_mode = "[cyan]VAD[/] (auto-detect speech)" if vad else f"Push-to-talk: [cyan]{config.hotkey.key}[/]"
    wake_str = f"Wake word: [cyan]{wake_word}[/]\n" if wake_word else ""

    # Format the hotkey nicely
    hotkey = config.hotkey.key
    if hotkey in ("KEY_LEFTMETA", "KEY_RIGHTMETA"):
        if sys.platform == "darwin":
            hotkey_display = "⌘ (Command)"
        else:
            hotkey_display = "Super/Meta"
    elif hotkey == "KEY_SCROLLLOCK":
        hotkey_display = "Scroll Lock"
    else:
        # Remove KEY_ prefix for cleaner display
        hotkey_display = hotkey.replace("KEY_", "")

    console.print(
        Panel(
            f"[bold green]voxtype[/] v{__version__}\n\n"
            f"Input: {input_mode}\n"
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
    )

    try:
        app.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/]")
        app.stop()
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

        table.add_row(result.name, status, result.message)

    console.print(table)
    console.print()

    if all_ok:
        console.print("[green]All required dependencies are available![/]")
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
    import sys
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

def main() -> None:
    """Entry point for the CLI."""
    app()

if __name__ == "__main__":
    main()
