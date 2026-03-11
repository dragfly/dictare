"""Transcribe command — print voice transcriptions to stdout."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Annotated

import typer

from dictare.cli._helpers import console


def process_messages(
    messages: Iterator,
    *,
    auto_submit: bool = False,
    output=sys.stdout,
    verbose: bool = False,
) -> None:
    """Process SSE messages and print transcriptions.

    Args:
        messages: Iterator of OpenVIP messages.
        auto_submit: If True, print each transcription immediately.
            If False, accumulate until submit.
        output: Output stream (default: stdout).
        verbose: If True, echo output to stderr.
    """
    buffer: list[str] = []

    try:
        for msg in messages:
            if msg.type != "transcription":
                continue

            text = msg.text or ""

            # Check for submit op — x_input is a MessageXInput object on real
            # Transcription models, or a dict in additional_properties for mocks.
            x_input = getattr(msg, "x_input", None)
            if x_input is None:
                x_input = getattr(msg, "additional_properties", {}).get("x_input")
            is_submit = False
            if x_input is not None:
                ops = x_input.get("ops") if isinstance(x_input, dict) else getattr(x_input, "ops", None)
                is_submit = "submit" in (ops or [])

            if auto_submit:
                if text.strip():
                    print(text, file=output, flush=True)
                    if verbose:
                        print(f"[transcribe] {text}", file=sys.stderr)
            else:
                if text:
                    buffer.append(text)
                if is_submit and buffer:
                    line = " ".join(buffer)
                    print(line, file=output, flush=True)
                    if verbose:
                        print(f"[transcribe] {line}", file=sys.stderr)
                    buffer = []
                    return
    finally:
        # Flush remaining buffer (even on KeyboardInterrupt)
        if buffer:
            line = " ".join(buffer)
            print(line, file=output, flush=True)
            if verbose:
                print(f"[transcribe] {line}", file=sys.stderr)


def register(app: typer.Typer) -> None:
    """Register transcribe command on the main app."""

    @app.command()
    def transcribe(
        agent_id: Annotated[
            str,
            typer.Option("--agent-id", "-a", help="Agent ID to register as"),
        ] = "transcribe",
        auto_submit: Annotated[
            bool,
            typer.Option(
                "--auto-submit",
                help="Print each transcription immediately (don't wait for submit)",
            ),
        ] = False,
        url: Annotated[
            str | None,
            typer.Option("--url", "-u", help="OpenVIP server URL"),
        ] = None,
        verbose: Annotated[
            bool,
            typer.Option("--verbose", "-v", help="Echo output to stderr (useful in pipes)"),
        ] = False,
    ) -> None:
        """Print voice transcriptions to stdout.

        Registers as an OpenVIP agent and outputs transcribed text.
        Use with pipes to feed voice into other commands.

        Examples:
            dictare transcribe | llm | dictare speak
            dictare transcribe --auto-submit
            dictare transcribe --agent-id my-agent | cat
        """
        from openvip import Client, DuplicateAgentError

        from dictare.config import load_config

        config = load_config()
        if url is None:
            url = f"http://{config.server.host}:{config.server.port}/openvip"

        client = Client(url, timeout=5)

        if not client.is_available():
            console.print(f"[red]Engine not available at {url}[/]", highlight=False)
            console.print("[dim]Start it with: dictare service start[/]")
            raise typer.Exit(1)

        # Info on stderr so stdout stays clean for piping
        if auto_submit:
            print(f"Listening as agent '{agent_id}'... (Ctrl+C to stop)", file=sys.stderr)
        else:
            print(f"Listening as agent '{agent_id}'... (submit to send)", file=sys.stderr)

        try:
            process_messages(
                client.subscribe(agent_id, reconnect=True),
                auto_submit=auto_submit,
                verbose=verbose,
            )
        except DuplicateAgentError:
            console.print(
                f"[red]Agent '{agent_id}' is already connected.[/]",
                highlight=False,
            )
            raise typer.Exit(1)
        except KeyboardInterrupt:
            pass
