"""Speak command — text-to-speech."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

import typer

from dictare.cli._helpers import console

logger = logging.getLogger(__name__)


# Kokoro voice name convention: {lang_prefix}{gender}_{name}
_KOKORO_LANG_PREFIX: dict[str, str] = {
    "a": "EN-US",
    "b": "EN-GB",
    "e": "ES",
    "f": "FR",
    "h": "HI",
    "i": "IT",
    "j": "JA",
    "p": "PT",
    "z": "ZH",
}

_KOKORO_GENDER: dict[str, str] = {
    "f": "F",
    "m": "M",
}


def _print_voices(engine_name: str, voices: list[str]) -> None:
    """Pretty-print a list of voice names."""
    console.print(f"[bold]{engine_name} voices ({len(voices)}):[/]\n")

    for v in voices:
        # Kokoro names follow {lang}{gender}_{name} convention
        if len(v) > 3 and v[2] == "_":
            lang_code = _KOKORO_LANG_PREFIX.get(v[0], "??")
            gender = _KOKORO_GENDER.get(v[1], "?")
            name = v[3:]
            console.print(f"  [cyan]{v:20}[/] {lang_code:5}  {gender}  {name}")
        else:
            console.print(f"  [cyan]{v}[/]")

    console.print("\n[dim]Use: dictare speak \"text\" -v <voice_name>[/]")


def _list_voices(engine_override: str | None, config_file: Path | None) -> None:
    """List available voices for the current TTS engine."""
    import json as _json
    import urllib.error
    import urllib.request

    from dictare.config import load_config

    config = load_config(config_file)
    engine_name = engine_override or config.tts.engine

    # Try the running engine API first
    url = f"http://{config.server.host}:{config.server.port}/speech/voices"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read())
        voices = data.get("voices", [])
        name = data.get("engine", engine_name)
        if voices:
            _print_voices(name, voices)
            return
        console.print(f"[dim]{name}: no voices available[/]")
        return
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        pass  # Engine not running — try offline

    console.print("[dim]Engine not running. Start it for voice listing.[/]")
    console.print("[dim]  dictare service start[/]")


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
            typer.Option("--engine", "-e", help="TTS engine: espeak, say, piper, coqui, outetts"),
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
        list_voices: Annotated[
            bool,
            typer.Option("--list-voices", help="List available voices for the current TTS engine"),
        ] = False,
    ) -> None:
        """Speak text using text-to-speech via the running engine.

        Examples:
            dictare speak "Hello world"
            echo "Hello world" | dictare speak
            llm "Tell me a joke" | dictare speak --engine say
            dictare speak --list-engines
        """
        import sys

        from dictare.config import TTSConfig, load_config

        # List engines mode
        if list_engines:
            console.print("[bold]Available TTS engines:[/]\n")
            engines_info = [
                ("espeak", "Basic TTS", "Many", "System: brew install espeak"),
                ("say", "macOS built-in", "Many", "macOS only"),
                ("piper", "Neural TTS", "Many", "pip: piper-tts"),
                ("coqui", "Neural TTS (XTTS)", "8+", "pip: TTS"),
                ("outetts", "Neural TTS (MLX)", "24", "Apple Silicon, pip: mlx-audio"),
            ]
            for name, desc, langs, install in engines_info:
                console.print(f"  [cyan]{name:10}[/] {desc:20} Languages: {langs:8} ({install})")
            console.print("\n[dim]Use: dictare speak \"text\" --engine <name>[/]")
            raise typer.Exit(0)

        # List voices mode
        if list_voices:
            _list_voices(engine, config_file)
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
        valid_engines = ("espeak", "say", "piper", "coqui", "outetts", "kokoro")
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

        # Speak via running engine — no in-process fallback.
        # TTS engines (coqui, piper, outetts, kokoro) run in the engine's
        # worker subprocess with their own isolated venv.
        import json as _json
        import urllib.error

        from openvip import Client

        try:
            client = Client(
                f"http://{config.server.host}:{config.server.port}",
                timeout=30.0,
            )
            kwargs: dict[str, Any] = {
                "engine": tts_config.engine,
                "speed": tts_config.speed,
            }
            # Only pass language when user explicitly specified -l.
            # The worker already knows its configured language; passing the
            # default "en" here would override voice-inferred language.
            if language:
                kwargs["language"] = language
            if tts_config.voice:
                kwargs["voice"] = tts_config.voice
            response = client.speak(text, **kwargs)
            if not quiet:
                duration = response.duration_ms or "?"
                console.print(f"[dim]Spoken via engine ({duration}ms)[/]")
            return
        except urllib.error.HTTPError as e:
            # Engine returned an error (422, 500, etc.)
            detail = ""
            try:
                body = _json.loads(e.read().decode())
                detail = body.get("detail", str(body))
            except Exception:
                detail = str(e)
            logger.error("TTS failed (HTTP %d): %s", e.code, detail)
            if not quiet:
                console.print(f"[red]TTS failed: {detail}[/]")
            raise typer.Exit(1)
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            logger.debug("Engine not reachable for TTS")
            if not quiet:
                console.print("[red]Engine not running.[/]")
                console.print("[dim]Start it with: dictare service start[/]")
            raise typer.Exit(1)
        except Exception as e:
            logger.error("TTS error: %s", e, exc_info=True)
            if not quiet:
                console.print(f"[red]TTS error: {e}[/]")
            raise typer.Exit(1)
