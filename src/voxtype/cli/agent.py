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
        continue_session: bool = False
        live_dangerously: bool = False
        has_double_dash = False  # tracks whether '--' separator was used
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
            elif arg in ("--continue", "-C"):
                continue_session = True
                own_flags_to_remove.add(i)
            elif arg == "--live-dangerously":
                live_dangerously = True
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
                has_double_dash = True
                own_flags_to_remove.add(i)

        command_override = [arg for i, arg in enumerate(args) if i not in own_flags_to_remove]

        # If there are leftover flag-like args (--foo) without an explicit '--' separator,
        # they are almost certainly mistyped voxtype options — reject with a clear message.
        if command_override and not has_double_dash:
            unknown_flags = [a for a in command_override if a.startswith("-")]
            if unknown_flags:
                console.print(f"[red]Error: unrecognized option(s): {' '.join(unknown_flags)}[/]")
                console.print("[dim]voxtype agent options: --type/-t <type>, --continue/-C, --live-dangerously, --server/-s <url>, --verbose, --quiet, --no-status-bar[/]")
                console.print("[dim]To pass flags to the agent command:  voxtype agent <name> -- <command> [flags][/]")
                raise typer.Exit(1)

        # Resolve command: explicit override > --type > default_agent_type > error
        resolved_agent_type = None
        if command_override:
            command = command_override
        else:
            type_key = agent_type_name or config.agent_types.default
            if type_key is None:
                console.print("[red]Error: no --type given and no agent_types.default set[/]")
                console.print(f"[dim]  voxtype agent {agent_id} --type <type>[/]")
                console.print(f"[dim]  voxtype agent {agent_id} -- <command> [args...][/]")
                if config.agent_types:
                    console.print()
                    console.print("[dim]Available types:[/]")
                    for name, at in config.agent_types.items():
                        desc = f"  {at.description}" if at.description else ""
                        console.print(f"[dim]  {name}{desc}[/]")
                raise typer.Exit(1)

            resolved_agent_type = config.agent_types.get(type_key)
            if resolved_agent_type is None:
                console.print(f"[red]Error: agent type '{type_key}' not found in config[/]")
                if config.agent_types:
                    console.print()
                    console.print("[dim]Available types:[/]")
                    for name, at in config.agent_types.items():
                        desc = f"  {at.description}" if at.description else ""
                        console.print(f"[dim]  {name}{desc}[/]")
                raise typer.Exit(1)

            command = list(resolved_agent_type.command)

        # Apply --continue: insert continue_args after argv[0]
        if continue_session:
            if resolved_agent_type is not None and resolved_agent_type.continue_args:
                command = [command[0]] + resolved_agent_type.continue_args + command[1:]
            elif resolved_agent_type is not None:
                console.print("[yellow]Warning: --continue given but agent type has no continue_args configured[/]")
            # With command override (--), --continue is silently ignored — user controls the full command

        # Apply --live-dangerously: insert live_dangerously_args after argv[0]
        if live_dangerously:
            if resolved_agent_type is not None and resolved_agent_type.live_dangerously_args:
                command = [command[0]] + resolved_agent_type.live_dangerously_args + command[1:]
            elif resolved_agent_type is not None:
                console.print("[yellow]Warning: --live-dangerously given but agent type has no live_dangerously_args configured[/]")
            # With command override (--), --live-dangerously is silently ignored

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
            claim_key=config.client.claim_key,
        )
        raise typer.Exit(exit_code)
