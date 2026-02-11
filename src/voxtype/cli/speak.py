"""Speak command — text-to-speech."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from voxtype.cli._helpers import console

def register(app: typer.Typer) -> None:
    """Register speak command on the main app."""

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
        no_engine: Annotated[
            bool,
            typer.Option("--no-engine", help="Force in-process TTS (skip running engine even if available)"),
        ] = False,
    ) -> None:
        """Speak text using text-to-speech.

        Examples:
            voxtype speak "Hello world"
            echo "Hello world" | voxtype speak
            llm "Tell me a joke" | voxtype speak --engine say
            voxtype speak --list-engines
            voxtype speak "Hello" --no-engine  # Force in-process
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

        # Try to use running engine via HTTP /speech if available
        if not no_engine:
            import urllib.error

            from openvip import Client

            try:
                client = Client(
                    f"http://{config.server.host}:{config.server.port}",
                    timeout=30.0,
                )
                response = client.speak(
                    text,
                    language=tts_config.language,
                    engine=tts_config.engine,
                    voice=tts_config.voice or None,
                    speed=tts_config.speed,
                )
                if not quiet:
                    duration = response.duration_ms or "?"
                    console.print(f"[dim]Spoken via engine ({duration}ms)[/]")
                return
            except (urllib.error.URLError, ConnectionRefusedError, OSError):
                pass  # Engine not running, fall through to in-process
            except Exception as e:
                if not quiet:
                    console.print(f"[yellow]Engine unavailable: {e}[/]")
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
