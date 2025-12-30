"""CLI interface for claude-mic."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from claude_mic import __version__
from claude_mic.config import create_default_config, get_config_path, load_config

app = typer.Typer(
    name="claude-mic",
    help="Voice-to-text for Claude Code CLI",
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
        console.print(f"claude-mic version {__version__}")
        raise typer.Exit()

@app.callback()
def main_callback(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-V", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """claude-mic: Voice-to-text for Claude Code CLI."""
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
    enter: Annotated[
        bool,
        typer.Option("--enter", "-e", help="Auto-press Enter after typing"),
    ] = False,
    clipboard: Annotated[
        bool,
        typer.Option("--clipboard", "-C", help="Use clipboard instead of typing (for accented chars)"),
    ] = False,
    gpu: Annotated[
        bool,
        typer.Option("--gpu", "-g", help="Use GPU (CUDA) for faster transcription"),
    ] = False,
    max_duration: Annotated[
        Optional[int],
        typer.Option("--max-duration", "-d", help="Max recording duration in seconds (default 60)"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
) -> None:
    """Start claude-mic in push-to-talk mode.

    Hold the configured key while speaking, release to transcribe and inject.
    """
    config = load_config(config_file)

    # Override config with CLI options
    if model:
        config.stt.model_size = model
    if key:
        config.hotkey.key = key
    if language:
        config.stt.language = language
    if enter:
        config.injection.auto_enter = True
    if clipboard:
        config.injection.backend = "clipboard"
    if gpu:
        config.stt.device = "cuda"
        config.stt.compute_type = "float16"  # Better for GPU
        _setup_cuda_library_path()
    if max_duration:
        config.audio.max_duration = max_duration
    if verbose:
        config.verbose = verbose

    # Lazy import to speed up CLI
    from claude_mic.core.app import ClaudeMicApp

    mic_app = ClaudeMicApp(config)

    mode_str = "[yellow]clipboard[/] (Ctrl+V to paste)" if clipboard else "keyboard"
    device_str = "[magenta]GPU (CUDA)[/]" if config.stt.device == "cuda" else "CPU"
    console.print(
        Panel(
            f"[bold green]claude-mic[/] v{__version__}\n\n"
            f"Push-to-talk key: [cyan]{config.hotkey.key}[/]\n"
            f"STT model: [cyan]{config.stt.model_size}[/] on {device_str}\n"
            f"Language: [cyan]{config.stt.language}[/]\n"
            f"Output mode: {mode_str}\n\n"
            f"Press [bold]Ctrl+C[/] to exit",
            title="Ready",
            border_style="green",
        )
    )

    try:
        mic_app.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/]")
        mic_app.stop()

@app.command()
def check() -> None:
    """Check system dependencies and configuration."""
    from claude_mic.utils.platform import check_dependencies

    console.print(Panel("[bold]Checking dependencies...[/]", border_style="blue"))
    console.print()

    results = check_dependencies()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    all_ok = True
    for result in results:
        if result.available:
            status = "[green]OK[/]"
        elif result.required:
            status = "[red]MISSING[/]"
            all_ok = False
        else:
            status = "[yellow]OPTIONAL[/]"

        table.add_row(result.name, status, result.message)

    console.print(table)
    console.print()

    if all_ok:
        console.print("[green]All required dependencies are available![/]")
    else:
        console.print("[red]Some required dependencies are missing.[/]")
        console.print("Please install the missing dependencies and try again.")
        raise typer.Exit(1)

    # Check for at least one text injection method
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

@app.command()
def config() -> None:
    """Show current configuration."""
    config_path = get_config_path()

    if not config_path.exists():
        console.print(f"[yellow]No config file found at {config_path}[/]")
        console.print("Run [cyan]claude-mic init[/] to create one.")
        return

    cfg = load_config()

    table = Table(show_header=True, header_style="bold", title="Current Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("Config file", str(config_path))
    table.add_row("STT backend", cfg.stt.backend)
    table.add_row("STT model", cfg.stt.model_size)
    table.add_row("Language", cfg.stt.language)
    table.add_row("Hotkey", cfg.hotkey.key)
    table.add_row("Injection backend", cfg.injection.backend)
    table.add_row("Clipboard fallback", str(cfg.injection.fallback_to_clipboard))

    console.print(table)

def main() -> None:
    """Entry point for the CLI."""
    app()

if __name__ == "__main__":
    main()
