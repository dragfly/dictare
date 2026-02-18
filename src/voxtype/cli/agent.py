"""Agent command — run a command with voice input via OpenVIP SSE."""

from __future__ import annotations

from typing import Annotated

import typer

from voxtype.cli._helpers import console


def _check_engine(url: str) -> bool:
    """Return True if the engine is reachable at *url*."""
    from openvip import Client

    return Client(url, timeout=2).is_available()


def _try_start_service() -> None:
    """Best-effort: ask launchd/systemd to start the engine service.

    Does NOT wait for the engine to become reachable — the SSE reconnect
    loop handles that.
    """
    import sys

    try:
        if sys.platform == "darwin":
            from voxtype.daemon.launchd import is_installed, start
        elif sys.platform == "linux":
            from voxtype.daemon.systemd import is_installed, start
        else:
            return

        if is_installed():
            start()
    except Exception:
        pass


def register(app: typer.Typer) -> None:
    """Register agent command on the main app."""

    @app.command(
        context_settings={"allow_extra_args": True, "allow_interspersed_args": False}
    )
    def agent(
        ctx: typer.Context,
        agent_id: Annotated[
            str | None,
            typer.Argument(help="Agent session name — identifies this instance (e.g., 'frontend', 'Pippo')"),
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
        """Launch an agent with voxtype voice input.

        AGENT_ID is the session name (project, role, etc.) — not the model type.
        Use --type to pick which agent_types template to run. Without --type,
        default_agent_type from config is used.

        Examples:

            voxtype agent frontend                         # Use default_agent_type
            voxtype agent frontend --type claude-sonnet    # Explicit type from config
            voxtype agent frontend -- claude --model opus  # Explicit command override
        """
        from voxtype.agent import run_agent
        from voxtype.config import load_config

        config = load_config()
        if server is None:
            server = config.client.url

        # agent_id (session name) is required
        if agent_id is None:
            import click

            click.echo(ctx.get_help())
            if config.agent_types:
                console.print()
                console.print("[dim]Available agent types:[/]")
                for name, at in config.agent_types.items():
                    desc = f"  {at.description}" if at.description else ""
                    console.print(f"[dim]  {name}{desc}[/]")
            raise typer.Exit(1)

        # Parse extra args: extract own flags and command override
        args = list(ctx.args)
        own_flags_to_remove: set[int] = set()
        show_status_bar: bool | None = None
        agent_type_name: str | None = None
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
            elif arg in ("--type", "-t") and i + 1 < len(args):
                agent_type_name = args[i + 1]
                own_flags_to_remove.add(i)
                own_flags_to_remove.add(i + 1)
            elif arg == "--":
                own_flags_to_remove.add(i)

        command_override = [arg for i, arg in enumerate(args) if i not in own_flags_to_remove]

        # Resolve command: explicit override > --type > default_agent_type > error
        if command_override:
            command = command_override
        else:
            type_key = agent_type_name or config.default_agent_type
            if type_key is None:
                console.print(f"[red]Error: no --type given and no default_agent_type set[/]")
                console.print(f"[dim]  voxtype agent {agent_id} --type <type>[/]")
                console.print(f"[dim]  voxtype agent {agent_id} -- <command> [args...][/]")
                if config.agent_types:
                    console.print()
                    console.print("[dim]Available types:[/]")
                    for name, at in config.agent_types.items():
                        desc = f"  {at.description}" if at.description else ""
                        console.print(f"[dim]  {name}{desc}[/]")
                raise typer.Exit(1)

            agent_type = config.agent_types.get(type_key)
            if agent_type is None:
                console.print(f"[red]Error: agent type '{type_key}' not found in config[/]")
                if config.agent_types:
                    console.print()
                    console.print("[dim]Available types:[/]")
                    for name, at in config.agent_types.items():
                        desc = f"  {at.description}" if at.description else ""
                        console.print(f"[dim]  {name}{desc}[/]")
                raise typer.Exit(1)

            command = agent_type.command

        # Best-effort: try to start the engine if it's not reachable.
        # Never block — the SSE layer has its own reconnect loop.
        if not _check_engine(server):
            if not quiet:
                console.print("[dim]Engine not running, starting service...[/]")
            _try_start_service()  # fire-and-forget, don't gate on result

        # CLI flags override config
        if show_status_bar is None:
            show_status_bar = config.client.status_bar

        exit_code = run_agent(
            agent_id, command, quiet=quiet, verbose=verbose,
            base_url=server, status_bar=show_status_bar,
            clear_on_start=config.client.clear_on_start,
        )
        raise typer.Exit(exit_code)
