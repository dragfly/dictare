"""First-time setup command."""

from __future__ import annotations

import sys

import typer

from voxtype.cli._helpers import console


def _is_brew_service_active() -> bool:
    """Check if Homebrew is managing the voxtype service."""
    import subprocess

    try:
        result = subprocess.run(
            ["brew", "services", "list"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if line.startswith("voxtype") and "started" in line:
                return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def register(app: typer.Typer) -> None:
    """Register setup command on the main app."""

    @app.command()
    def setup() -> None:
        """First-time setup: config, models, service, tray, permissions.

        Installs and starts everything needed to use voxtype.
        For Homebrew users, this is optional (use 'brew services start voxtype').

        Example:
            voxtype setup
        """
        from voxtype.cli.models import ensure_required_models
        from voxtype.config import create_default_config, get_config_path, load_config

        # Step 1: Config
        config_path = get_config_path()
        if not config_path.exists():
            create_default_config()
            console.print(f"[green]✓[/] Created config: {config_path}")
        else:
            console.print(f"[dim]✓ Config exists: {config_path}[/]")

        config = load_config()

        # Step 2: Models
        console.print("[dim]Checking models...[/]")
        if not ensure_required_models(config):
            console.print("[red]✗ Model download failed. Run 'voxtype setup' again to retry.[/]")
            raise typer.Exit(1)
        console.print("[green]✓[/] Models ready")

        # Step 3: Service
        console.print("[dim]Installing service...[/]")
        try:
            if sys.platform == "darwin":
                from voxtype.daemon import launchd as backend
            elif sys.platform == "linux":
                from voxtype.daemon import systemd as backend
            else:
                console.print(f"[yellow]Skipping service install (unsupported platform: {sys.platform})[/]")
                return

            # Skip if Homebrew is already managing the service
            if _is_brew_service_active():
                console.print("[dim]✓ Service managed by Homebrew (brew services)[/]")
            elif not backend.is_installed():
                backend.install()
                if sys.platform == "linux":
                    backend.start()
                console.print("[green]✓[/] Service installed and started")
            else:
                console.print("[dim]✓ Service already installed[/]")
        except Exception as e:
            console.print(f"[yellow]Service install failed: {e}[/]")
            console.print("[dim]You can install manually: voxtype service install[/]")

        console.print()
        console.print("[bold green]Setup complete![/]")
        console.print()
        console.print("  Launch an agent:  [cyan]voxtype agent claude[/]")
        console.print("  Start tray icon:  [cyan]voxtype tray start[/]")
