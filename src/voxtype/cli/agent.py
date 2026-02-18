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
            typer.Argument(help="Agent name or template (e.g., 'claude')"),
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

        Uses agent templates from config for single-command launch.
        Auto-connects to the engine (starts it if the service is installed).

        Examples:

            voxtype agent claude                        # Use template from config
            voxtype agent claude -- claude --model opus # Override command
        """
        from voxtype.agent import run_agent
        from voxtype.config import load_config

        config = load_config()
        if server is None:
            server = config.client.url

        # Resolve agent_id: explicit arg > default_agent_type > help
        if agent_id is None:
            if config.default_agent_type:
                agent_id = config.default_agent_type
            else:
                import click

                click.echo(ctx.get_help())
                if config.agent_types:
                    console.print()
                    console.print("[dim]Available agent types:[/]")
                    for name, at in config.agent_types.items():
                        desc = f"  {at.description}" if at.description else ""
                        console.print(f"[dim]  {name}{desc}[/]")
                    console.print()
                    console.print("[dim]Set a default: voxtype config set default_agent_type claude[/]")
                raise typer.Exit(0)

        # Parse extra args: extract own flags and command override
        args = list(ctx.args)
        own_flags_to_remove: set[int] = set()
        show_status_bar: bool | None = None
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
            elif arg == "--":
                own_flags_to_remove.add(i)

        command_override = [arg for i, arg in enumerate(args) if i not in own_flags_to_remove]

        # Resolve command: explicit override > agent type > error
        agent_type = config.agent_types.get(agent_id)
        if command_override:
            command = command_override
        elif agent_type:
            command = agent_type.command
        else:
            console.print(f"[red]Error: No agent type '{agent_id}' in config and no command specified[/]")
            console.print()
            console.print("[dim]Either add an agent type to ~/.config/voxtype/config.toml:[/]")
            console.print(f'[dim]  [agent_types.{agent_id}][/]')
            console.print(f'[dim]  command = ["{agent_id}"][/]')
            console.print()
            console.print("[dim]Or specify the command explicitly:[/]")
            console.print(f"[dim]  voxtype agent {agent_id} -- {agent_id}[/]")
            raise typer.Exit(1)

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
