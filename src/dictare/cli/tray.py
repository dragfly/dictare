"""System tray management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from dictare.cli._helpers import console

app = typer.Typer(help="Manage the system tray.", no_args_is_help=True)

@app.command("start")
def tray_start(
    foreground: Annotated[
        bool,
        typer.Option("--foreground", "-f", help="Run in foreground (for debugging)"),
    ] = False,
) -> None:
    """Start the dictare system tray application.

    Shows an icon in the system tray/menu bar with controls for:
    - Start/Stop listening
    - Mute/Unmute
    - Target selection
    - Settings

    By default runs in background. Use --foreground for debugging.

    Example:
        dictare tray start              # Background (daemon mode)
        dictare tray start --foreground # Foreground (debug mode)
    """
    from dictare.tray.lifecycle import get_tray_status, start_tray

    # Check if already running
    status = get_tray_status()
    if status.running:
        console.print(f"[yellow]Tray already running[/] (PID: {status.pid})")
        raise typer.Exit(1)

    if foreground:
        console.print("[dim]Starting dictare tray (foreground)...[/]")
        console.print("[dim]Right-click the icon for menu. Ctrl+C to quit.[/]")

        result = start_tray(foreground=True)
        raise typer.Exit(result)
    else:
        # Background mode
        result = start_tray(foreground=False)
        if result == 0:
            import time

            time.sleep(0.3)
            status = get_tray_status()
            if status.running:
                console.print(f"[green]Tray started[/] (PID: {status.pid})")
            else:
                console.print("[red]Tray failed to start[/]")
                raise typer.Exit(1)
        else:
            console.print("[red]Tray failed to start[/]")
            raise typer.Exit(1)

@app.command("stop")
def tray_stop() -> None:
    """Stop the dictare system tray application.

    Example:
        dictare tray stop
    """
    from dictare.tray.lifecycle import get_tray_status, stop_tray

    status = get_tray_status()
    if not status.running:
        console.print("[yellow]Tray is not running[/]")
        raise typer.Exit(1)

    console.print(f"[dim]Stopping tray (PID: {status.pid})...[/]")
    result = stop_tray()

    if result == 0:
        console.print("[green]Tray stopped[/]")
    else:
        console.print("[red]Failed to stop tray[/]")
        raise typer.Exit(1)

@app.command("status")
def tray_status() -> None:
    """Show dictare tray status.

    Example:
        dictare tray status
    """
    from dictare.tray.lifecycle import get_tray_status

    status = get_tray_status()

    if status.running:
        console.print(f"[green]Tray running[/] (PID: {status.pid})")
    else:
        console.print("[dim]Tray not running[/]")
