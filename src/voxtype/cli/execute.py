"""Execute command — run a command with transcribed speech."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from voxtype.cli._helpers import auto_detect_acceleration, console


def register(app: typer.Typer) -> None:
    """Register execute command on the main app."""

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

        from voxtype.config import load_config

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
            auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

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
