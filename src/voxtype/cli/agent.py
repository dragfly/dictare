"""Agent command — run a command with voice input via OpenVIP SSE."""

from __future__ import annotations

from typing import Annotated

import typer

from voxtype.cli._helpers import console

def register(app: typer.Typer) -> None:
    """Register agent command on the main app."""

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
        verbose: Annotated[
            bool,
            typer.Option("--verbose", "-v", help="Log full text in session file (not truncated)"),
        ] = False,
        server: Annotated[
            str | None,
            typer.Option("--server", "-s", help="Engine HTTP server URL (default: from config)"),
        ] = None,
    ) -> None:
        """Run a command with voxtype voice input via OpenVIP SSE.

        Connects to the engine HTTP server via SSE to receive voice transcriptions.
        The SSE connection automatically registers the agent with the engine.

        Example:

            # Terminal 1: Start listening with agent mode
            voxtype listen --agents

            # Terminal 2: Start the agent wrapper
            voxtype agent claude -- claude
        """
        # Show help if no agent_id
        if agent_id is None:
            import click

            click.echo(ctx.get_help())
            raise typer.Exit(0)

        from voxtype.agent import run_agent
        from voxtype.config import load_config

        # Load config for defaults
        config = load_config()
        if server is None:
            server = config.client.url

        # With allow_interspersed_args=False, flags after positional args go to ctx.args.
        # Extract our own flags before passing the rest as the command.
        args = list(ctx.args)
        own_flags_to_remove: set[int] = set()
        show_status_bar: bool | None = None  # None = use config default
        tv_port: int | None = None
        for i, arg in enumerate(args):
            if arg in ("--verbose", "-v"):
                verbose = True
                own_flags_to_remove.add(i)
            elif arg in ("--quiet", "-q"):
                quiet = True
                own_flags_to_remove.add(i)
            elif arg == "--no-status-bar":
                show_status_bar = False
                own_flags_to_remove.add(i)
            elif arg in ("--server", "-s") and i + 1 < len(args):
                server = args[i + 1]
                own_flags_to_remove.add(i)
                own_flags_to_remove.add(i + 1)
            elif arg == "--tv" and i + 1 < len(args):
                tv_port = int(args[i + 1])
                own_flags_to_remove.add(i)
                own_flags_to_remove.add(i + 1)
            elif arg == "--":
                own_flags_to_remove.add(i)

        command = [arg for i, arg in enumerate(args) if i not in own_flags_to_remove]
        if not command:
            console.print("[red]Error: No command specified[/]")
            console.print()
            console.print("[dim]Usage: voxtype agent AGENT_ID -- COMMAND...[/]")
            console.print("[dim]Example: voxtype agent claude -- claude[/]")
            raise typer.Exit(1)

        # CLI flags override config
        if show_status_bar is None:
            show_status_bar = config.client.status_bar

        exit_code = run_agent(
            agent_id, command, quiet=quiet, verbose=verbose,
            base_url=server, status_bar=show_status_bar,
            clear_on_start=config.client.clear_on_start,
            terminal_viewer_port=tv_port,
        )
        raise typer.Exit(exit_code)
