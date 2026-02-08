"""Daemon management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from voxtype.cli._helpers import console
from voxtype.cli.models import check_required_models

app = typer.Typer(help="Manage the daemon.", no_args_is_help=True)

@app.command("start")
def daemon_start(
    foreground: Annotated[
        bool,
        typer.Option("--foreground", "-f", help="Run in foreground (for systemd/launchd)"),
    ] = False,
) -> None:
    """Start the voxtype daemon.

    The daemon keeps TTS/STT models loaded in memory for fast responses.

    Examples:
        voxtype daemon start              # Background
        voxtype daemon start --foreground # Foreground (for systemd/launchd)
    """
    from voxtype.daemon import get_daemon_status, start_daemon

    status = get_daemon_status()
    if status.running:
        console.print(f"[yellow]Daemon already running[/] (PID: {status.pid})")
        raise typer.Exit(0)

    # Quick check: verify required models are cached
    if not check_required_models(for_command="daemon"):
        raise typer.Exit(1)

    if foreground:
        console.print("[dim]Starting daemon in foreground...[/]")
        result = start_daemon(foreground=True)
    else:
        console.print("[dim]Starting daemon...[/]")
        result = start_daemon(foreground=False)

        if result == 0:
            # Verify it started
            import time

            time.sleep(0.5)
            status = get_daemon_status()
            if status.running:
                console.print(f"[green]Daemon started[/] (PID: {status.pid})")
            else:
                console.print("[red]Daemon failed to start[/]")
                console.print("[dim]Check logs: ~/.local/share/voxtype/daemon.log[/]")
                raise typer.Exit(1)
        else:
            console.print("[red]Failed to start daemon[/]")
            raise typer.Exit(1)

@app.command("stop")
def daemon_stop() -> None:
    """Stop the voxtype daemon."""
    from voxtype.daemon import get_daemon_status, stop_daemon

    status = get_daemon_status()
    if not status.running:
        console.print("[yellow]Daemon is not running[/]")
        raise typer.Exit(0)

    console.print(f"[dim]Stopping daemon (PID: {status.pid})...[/]")
    result = stop_daemon()

    if result == 0:
        console.print("[green]Daemon stopped[/]")
    else:
        console.print("[red]Failed to stop daemon[/]")
        raise typer.Exit(1)

@app.command("status")
def daemon_status_cmd() -> None:
    """Show daemon status."""
    from voxtype.daemon import get_daemon_status
    from voxtype.daemon.client import DaemonClient, is_daemon_running

    status = get_daemon_status()

    if not status.running:
        console.print("[yellow]Daemon is not running[/]")
        if status.socket_exists:
            console.print("[dim]Stale socket file exists (will be cleaned on next start)[/]")
        raise typer.Exit(0)

    console.print(f"[green]Daemon is running[/] (PID: {status.pid})")

    # Try to get detailed status from daemon
    if is_daemon_running():
        from voxtype.daemon.protocol import StatusResponse

        try:
            client = DaemonClient()
            response = client.get_status()

            if isinstance(response, StatusResponse):
                uptime = response.uptime_seconds
                if uptime < 60:
                    uptime_str = f"{uptime:.0f}s"
                elif uptime < 3600:
                    uptime_str = f"{uptime / 60:.1f}m"
                else:
                    uptime_str = f"{uptime / 3600:.1f}h"
                console.print(f"  State: {response.state}")
                console.print(f"  Uptime: {uptime_str}")
                console.print(f"  Requests served: {response.requests_served}")
                console.print(f"  Output mode: {response.output_mode}")
                # Always show agents info for debugging
                agents_list = response.available_agents or []
                console.print(f"  Agents: {len(agents_list)} available")
                if agents_list:
                    for agent in agents_list:
                        marker = " *" if agent == response.current_agent else ""
                        console.print(f"    - {agent}{marker}")
                console.print(f"  STT loaded: {'yes' if response.stt_loaded else 'no'}")
                console.print(f"  TTS loaded: {'yes' if response.tts_loaded else 'no'}")
                if response.tts_engine:
                    console.print(f"  TTS engine: {response.tts_engine}")
        except Exception as e:
            console.print(f"[dim]Could not get detailed status: {e}[/]")

@app.command("restart")
def daemon_restart(
    foreground: Annotated[
        bool,
        typer.Option("--foreground", "-f", help="Run in foreground after restart"),
    ] = False,
) -> None:
    """Restart the voxtype daemon."""
    from voxtype.daemon import get_daemon_status, start_daemon, stop_daemon

    status = get_daemon_status()
    if status.running:
        console.print(f"[dim]Stopping daemon (PID: {status.pid})...[/]")
        stop_daemon()

    console.print("[dim]Starting daemon...[/]")
    result = start_daemon(foreground=foreground)

    if result == 0 and not foreground:
        import time

        time.sleep(0.5)
        status = get_daemon_status()
        if status.running:
            console.print(f"[green]Daemon restarted[/] (PID: {status.pid})")
        else:
            console.print("[red]Daemon failed to start[/]")
            raise typer.Exit(1)
