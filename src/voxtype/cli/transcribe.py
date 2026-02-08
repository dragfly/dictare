"""Transcribe command — one-shot audio-to-text."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from voxtype.cli._helpers import auto_detect_acceleration


def register(app: typer.Typer) -> None:
    """Register transcribe command on the main app."""

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

        from voxtype.config import load_config

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
            auto_detect_acceleration(config, cpu_only=not config.stt.hw_accel)

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
