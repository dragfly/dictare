"""Agent command — run a command with voice input via OpenVIP SSE."""

from __future__ import annotations

import shutil
from typing import Annotated

import typer

from dictare.cli._helpers import console


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
            from dictare.daemon.launchd import is_installed, start
        elif sys.platform == "linux":
            from dictare.daemon.systemd import is_installed, start
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
        verbose: Annotated[
            bool,
            typer.Option("--verbose", "-v", help="Verbose agent logging and full text in session file"),
        ] = False,
        server: Annotated[
            str | None,
            typer.Option("--server", "-s", help="Engine HTTP server URL (default: from config)"),
        ] = None,
    ) -> None:
        """Launch an agent with dictare voice input.

        AGENT_ID is the session name (project, role, etc.) — not the model profile.
        Use --profile to pick which agent_profiles template to run. Without --profile,
        default agent profile from config is used.

        Examples:

            dictare agent frontend                            # Use default profile
            dictare agent frontend --profile claude-sonnet    # Explicit profile from config
            dictare agent frontend -- claude --model opus     # Explicit command override
        """
        from dictare.agent import run_agent
        from dictare.config import load_config

        config = load_config()
        if server is None:
            server = config.client.url

        # agent_id (session name) is required
        if agent_id is None:
            import os as _os

            import click

            from dictare.agent import session_registry

            click.echo(ctx.get_help())
            if config.agent_profiles:
                console.print()
                console.print("[dim]Available agent profiles:[/]")
                for name, at in config.agent_profiles.items():
                    desc = f"  {at.description}" if at.description else ""
                    console.print(f"[dim]  {name}{desc}[/]")
            recent = session_registry.list_entries(_os.getcwd())
            if recent:
                console.print()
                console.print("[dim]Sessions in this folder:[/]")
                for name, entry in recent:
                    profile = entry.get("profile", "?")
                    last = str(entry.get("last_used", ""))[:10]
                    console.print(f"[dim]  {name} ({profile}, last used {last})[/]")
                console.print("[dim]Resume one:  dictare agent <name> --continue[/]")
            raise typer.Exit(1)

        # Parse extra args: extract own flags and command override
        args = list(ctx.args)
        own_flags_to_remove: set[int] = set()
        agent_profile_name: str | None = None
        continue_session: bool = False
        live_dangerously: bool = False
        has_double_dash = False  # tracks whether '--' separator was used
        for i, arg in enumerate(args):
            if arg in ("--verbose", "-v"):
                verbose = True
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
            elif arg in ("--profile", "--type", "-t") and i + 1 < len(args):
                agent_profile_name = args[i + 1]
                own_flags_to_remove.add(i)
                own_flags_to_remove.add(i + 1)
            elif arg == "--":
                has_double_dash = True
                own_flags_to_remove.add(i)

        command_override = [arg for i, arg in enumerate(args) if i not in own_flags_to_remove]

        # If there are leftover flag-like args (--foo) without an explicit '--' separator,
        # they are almost certainly mistyped dictare options — reject with a clear message.
        if command_override and not has_double_dash:
            unknown_flags = [a for a in command_override if a.startswith("-")]
            if unknown_flags:
                console.print(f"[red]Error: unrecognized option(s): {' '.join(unknown_flags)}[/]")
                console.print("[dim]dictare agent options: --profile/-t <profile>, --continue/-C, --live-dangerously, --server/-s <url>, --verbose[/]")
                console.print("[dim]To pass flags to the agent command:  dictare agent <name> -- <command> [flags][/]")
                raise typer.Exit(1)

        # Named session continuity: best-effort per-folder memory of which
        # profile this session name was launched with. The registry is a
        # pointer — the agent's own session store stays the source of truth.
        import os as _os
        import sys as _sys

        from dictare.agent import session_registry

        cwd = _os.getcwd()
        registry_entry = (
            None if command_override else session_registry.lookup(cwd, agent_id)
        )
        if registry_entry:
            remembered = str(registry_entry.get("profile") or "")
            if continue_session and agent_profile_name is None and remembered:
                agent_profile_name = remembered
                console.print(
                    f"[dim]Resuming '{agent_id}' with remembered profile: {remembered}[/]"
                )
            elif (
                not continue_session
                and remembered
                and agent_profile_name in (None, remembered)
                and _sys.stdin.isatty()
            ):
                if typer.confirm(
                    f"A previous {remembered} session '{agent_id}' exists in "
                    "this folder — continue it?",
                    default=False,
                ):
                    continue_session = True
                    agent_profile_name = remembered

        # Resolve command: explicit override > --type > default_agent_type > error
        resolved_profile = None
        if command_override:
            command = command_override
        else:
            type_key = agent_profile_name or config.agent_profiles.default
            if type_key is None:
                console.print("[red]Error: no --profile given and no agent_profiles.default set[/]")
                console.print(f"[dim]  dictare agent {agent_id} --profile <profile>[/]")
                console.print(f"[dim]  dictare agent {agent_id} -- <command> [args...][/]")
                if config.agent_profiles:
                    console.print()
                    console.print("[dim]Available profiles:[/]")
                    for name, at in config.agent_profiles.items():
                        desc = f"  {at.description}" if at.description else ""
                        console.print(f"[dim]  {name}{desc}[/]")
                raise typer.Exit(1)

            resolved_profile = config.agent_profiles.get(type_key)
            if resolved_profile is None:
                console.print(f"[red]Error: agent profile '{type_key}' not found in config[/]")
                if config.agent_profiles:
                    console.print()
                    console.print("[dim]Available profiles:[/]")
                    for name, at in config.agent_profiles.items():
                        desc = f"  {at.description}" if at.description else ""
                        console.print(f"[dim]  {name}{desc}[/]")
                raise typer.Exit(1)

            command = list(resolved_profile.command)

        # Check that the agent binary is installed (only for profile-resolved commands)
        binary = command[0] if command else None
        if binary and not command_override and not shutil.which(binary):
            console.print(f"[yellow]The default agent profile is '{type_key}', but '{binary}' is not installed.[/]")
            console.print()
            if config.agent_profiles:
                console.print("[dim]Available profiles:[/]")
                for name, at in config.agent_profiles.items():
                    bin_name = at.command[0] if at.command else "?"
                    installed = "[green]installed[/]" if shutil.which(bin_name) else "[red]not found[/]"
                    console.print(f"  [bold]{name}[/] ({bin_name} {installed})")
                    console.print(f"    [dim]dictare agent {agent_id} --profile {name}[/]")
                console.print()
            console.print("[dim]Or run any command directly:[/]")
            console.print(f"[dim]  dictare agent {agent_id} -- <command> [args...][/]")
            raise typer.Exit(1)

        # Merge CLI flag with config defaults (profile overrides global)
        if not live_dangerously and resolved_profile is not None:
            if resolved_profile.live_dangerously is not None:
                live_dangerously = resolved_profile.live_dangerously
            else:
                live_dangerously = config.agent_profiles.live_dangerously

        # Per-agent session adapter: exact resume / bindable new session.
        # Keyed on the command binary so custom profiles get it for free.
        from dictare.agent import session_adapters

        adapter = (
            session_adapters.get_adapter(command[0])
            if not command_override
            else None
        )
        launch_binding: dict[str, str] = {}

        # Apply --continue: exact adapter resume when bound, else the
        # profile's plain continue_args (phase 1 behavior)
        if continue_session:
            exact_resume = (
                adapter.resume_args(registry_entry)
                if adapter and registry_entry
                else None
            )
            if exact_resume is not None:
                command = [command[0]] + exact_resume + command[1:]
            elif resolved_profile is not None and resolved_profile.continue_args:
                command = [command[0]] + resolved_profile.continue_args + command[1:]
            elif resolved_profile is not None:
                console.print("[yellow]Warning: --continue given but agent profile has no continue_args configured[/]")
            # With command override (--), --continue is silently ignored — user controls the full command
        elif adapter is not None:
            # New session: let the adapter make it bindable (e.g. assign the
            # session UUID) so a future --continue resumes exactly this one.
            plan = adapter.new_session(cwd, agent_id)
            if plan.extra_args:
                command = [command[0]] + plan.extra_args + command[1:]
            launch_binding = plan.binding

        # Apply --live-dangerously: insert live_dangerously_args after argv[0]
        applied_danger_args: list[str] | None = None
        if live_dangerously:
            if resolved_profile is not None and resolved_profile.live_dangerously_args:
                applied_danger_args = resolved_profile.live_dangerously_args
                command = [command[0]] + applied_danger_args + command[1:]
                console.print(
                    f"[yellow]⚠ live-dangerously: {' '.join(applied_danger_args)}[/]"
                )
            elif resolved_profile is not None:
                console.print("[yellow]Warning: --live-dangerously given but agent profile has no live_dangerously_args configured[/]")
            # With command override (--), --live-dangerously is silently ignored

        # Try to auto-start the engine if not reachable.
        if not _check_engine(server):
            console.print("[dim]Engine not running, starting service...[/]")
            _try_start_service()
            # Wait up to 10s for engine to become reachable
            import time
            for _ in range(20):
                time.sleep(0.5)
                if _check_engine(server):
                    break
            # run_agent() will do a final check and error out if still unreachable

        # Remember (folder, name) → profile for future --continue launches
        if not command_override and type_key:
            session_registry.record_launch(
                cwd, agent_id, type_key, extra=launch_binding
            )

        import time as _time

        launched_at = _time.time()
        exit_code = run_agent(
            agent_id, command, verbose=verbose,
            base_url=server,
            clear_on_start=config.client.clear_on_start,
            claim_key=config.client.claim_key,
            info_key=config.client.info_key,
            global_hotkey_key=config.hotkey.key,
            live_dangerously_args=applied_danger_args,
        )

        # Post-exit discovery for adapters that cannot assign the session
        # identity at launch (codex, pi). Only fills a missing binding —
        # an id assigned at launch is already stable across resumes.
        if adapter is not None and not command_override and type_key:
            entry = session_registry.lookup(cwd, agent_id) or {}
            if not (
                launch_binding
                or entry.get("session_id")
                or entry.get("session_path")
            ):
                discovered = adapter.discover_binding(cwd, launched_at)
                if discovered:
                    session_registry.update_entry(cwd, agent_id, discovered)

        raise typer.Exit(exit_code)
