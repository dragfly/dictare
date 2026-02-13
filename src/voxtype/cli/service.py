"""System service management commands."""

from __future__ import annotations

import sys

import typer

from voxtype.cli._helpers import console

app = typer.Typer(help="Manage voxtype as a system service.", no_args_is_help=True)

def _get_backend():
    """Return the platform-specific service backend module."""
    if sys.platform == "darwin":
        from voxtype.service import launchd

        return launchd
    elif sys.platform == "linux":
        from voxtype.service import systemd

        return systemd
    else:
        console.print(f"[red]Unsupported platform: {sys.platform}[/]")
        raise typer.Exit(1)

@app.command("install")
def service_install() -> None:
    """Install and start voxtype as a system service (auto-start at login)."""
    backend = _get_backend()
    if backend.is_installed():
        console.print("[yellow]Service already installed[/]")
        raise typer.Exit(0)

    console.print("[dim]Installing service...[/]")
    try:
        backend.install()
        # On macOS, install() already loads the agent (= starts it).
        # On Linux, we need an explicit start after install.
        if sys.platform == "linux":
            backend.start()
    except Exception as e:
        console.print(f"[red]Failed to install service: {e}[/]")
        raise typer.Exit(1)
    console.print("[green]Service installed and started[/]")

@app.command("uninstall")
def service_uninstall() -> None:
    """Stop and remove the voxtype system service."""
    backend = _get_backend()
    if not backend.is_installed():
        console.print("[yellow]Service is not installed[/]")
        raise typer.Exit(0)

    console.print("[dim]Uninstalling service...[/]")
    try:
        backend.uninstall()
    except Exception as e:
        console.print(f"[red]Failed to uninstall service: {e}[/]")
        raise typer.Exit(1)
    console.print("[green]Service uninstalled[/]")

@app.command("start")
def service_start() -> None:
    """Start the voxtype service."""
    backend = _get_backend()
    if not backend.is_installed():
        console.print("[red]Service is not installed. Run 'voxtype service install' first.[/]")
        raise typer.Exit(1)

    try:
        backend.start()
    except Exception as e:
        console.print(f"[red]Failed to start service: {e}[/]")
        raise typer.Exit(1)
    console.print("[green]Service started[/]")

@app.command("stop")
def service_stop() -> None:
    """Stop the voxtype service."""
    backend = _get_backend()
    if not backend.is_installed():
        console.print("[red]Service is not installed[/]")
        raise typer.Exit(1)

    try:
        backend.stop()
    except Exception as e:
        console.print(f"[red]Failed to stop service: {e}[/]")
        raise typer.Exit(1)
    console.print("[green]Service stopped[/]")

@app.command("status")
def service_status() -> None:
    """Show service status."""
    backend = _get_backend()
    if not backend.is_installed():
        console.print("[yellow]Service is not installed[/]")
        raise typer.Exit(0)

    console.print("[green]Service is installed[/]")

    # Check if service is loaded (macOS: launchd, Linux: systemd active)
    loaded = backend.is_loaded() if hasattr(backend, "is_loaded") else True
    if not loaded:
        console.print("  Engine: [dim]stopped[/] (service not loaded)")
        return

    # Service is loaded — check engine HTTP status
    from openvip import Client

    from voxtype.config import load_config

    try:
        config = load_config()
        client = Client(
            f"http://{config.server.host}:{config.server.port}",
            timeout=2,
        )
        status = client.get_status()
        platform = status.platform or {}
        console.print(f"  Engine: [green]running[/] ({platform.get('mode', '?')})")
        console.print(f"  Version: {platform.get('version', '?')}")
    except (ConnectionRefusedError, OSError):
        console.print("  Engine: [yellow]not responding[/]")
    except Exception as e:
        console.print(f"  Engine: [red]error[/] ({e})")

@app.command("logs")
def service_logs() -> None:
    """Show recent service logs."""
    if sys.platform == "darwin":
        from voxtype.service.launchd import LOG_DIR

        for name in ("stderr.log", "stdout.log"):
            log_file = LOG_DIR / name
            if log_file.exists():
                console.print(f"[bold]--- {name} ---[/]")
                lines = log_file.read_text().splitlines()
                for line in lines[-30:]:
                    console.print(line)
            else:
                console.print(f"[dim]{name}: not found[/]")
    elif sys.platform == "linux":
        import subprocess

        result = subprocess.run(
            ["journalctl", "--user", "-u", "voxtype.service", "-n", "30", "--no-pager"],
            capture_output=True,
            text=True,
        )
        console.print(result.stdout or result.stderr or "[dim]No logs found[/]")
    else:
        console.print(f"[red]Unsupported platform: {sys.platform}[/]")
