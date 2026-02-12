"""Agent command — run a command with voice input via OpenVIP SSE."""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Annotated

import typer

from voxtype.cli._helpers import console


def _check_engine(url: str) -> bool:
    """Return True if the engine is reachable at *url*."""
    try:
        with urllib.request.urlopen(f"{url}/status", timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _try_start_service() -> bool:
    """Attempt to start the voxtype service. Return True on success."""
    import sys
    import time

    try:
        if sys.platform == "darwin":
            from voxtype.service.launchd import is_installed, start
        elif sys.platform == "linux":
            from voxtype.service.systemd import is_installed, start
        else:
            return False

        if not is_installed():
            return False

        start()
        # Give the engine a moment to bind the HTTP port
        for _ in range(20):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen("http://127.0.0.1:8770/status", timeout=1):
                    return True
            except (urllib.error.URLError, OSError):
                continue
        return False
    except Exception:
        return False


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
        # Show help if no agent_id
        if agent_id is None:
            import click

            click.echo(ctx.get_help())
            raise typer.Exit(0)

        from voxtype.agent import run_agent
        from voxtype.config import load_config

        config = load_config()
        if server is None:
            server = config.client.url

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

        # Resolve command: explicit override > template > error
        template = config.agents.get(agent_id)
        if command_override:
            command = command_override
        elif template:
            command = template.command
        else:
            console.print(f"[red]Error: No template '{agent_id}' in config and no command specified[/]")
            console.print()
            console.print("[dim]Either add a template to ~/.config/voxtype/config.toml:[/]")
            console.print(f'[dim]  [agents.{agent_id}][/]')
            console.print(f'[dim]  command = ["{agent_id}"][/]')
            console.print()
            console.print("[dim]Or specify the command explicitly:[/]")
            console.print(f"[dim]  voxtype agent {agent_id} -- {agent_id}[/]")
            raise typer.Exit(1)

        # Health check: is the engine running?
        if not _check_engine(server):
            if not quiet:
                console.print("[dim]Engine not running, starting service...[/]")
            if _try_start_service():
                if not quiet:
                    console.print("[green]Engine started[/]")
            else:
                console.print("[red]Error: Engine is not running[/]")
                console.print()
                console.print("[dim]Start it manually:[/]")
                console.print("[dim]  voxtype engine start -d --agents[/]")
                console.print()
                console.print("[dim]Or install as a service:[/]")
                console.print("[dim]  voxtype service install[/]")
                raise typer.Exit(1)

        # CLI flags override config
        if show_status_bar is None:
            show_status_bar = config.client.status_bar

        exit_code = run_agent(
            agent_id, command, quiet=quiet, verbose=verbose,
            base_url=server, status_bar=show_status_bar,
            clear_on_start=config.client.clear_on_start,
        )
        raise typer.Exit(exit_code)
