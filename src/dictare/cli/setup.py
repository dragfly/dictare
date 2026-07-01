"""First-time setup command."""

from __future__ import annotations

import typer

from dictare.cli._helpers import console


def register(app: typer.Typer) -> None:
    """Register setup command on the main app."""

    @app.command()
    def setup() -> None:
        """First-time setup: config, models, service, tray, permissions.

        Installs and starts everything needed to use dictare.
        Example:
            dictare setup
        """
        import sys

        from dictare.cli.models import ensure_required_models
        from dictare.config import create_default_config, get_config_path, load_config

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
            console.print("[red]✗ Model download failed. Run 'dictare setup' again to retry.[/]")
            raise typer.Exit(1)
        console.print("[green]✓[/] Models ready")

        # Step 3: Service
        console.print("[dim]Installing service...[/]")
        try:
            if sys.platform == "darwin":
                from dictare.daemon import launchd as backend
            elif sys.platform == "linux":
                from dictare.daemon import systemd as backend
            else:
                console.print(f"[yellow]Skipping service install (unsupported platform: {sys.platform})[/]")
                return

            if not backend.is_installed():
                backend.install()
                if sys.platform == "linux":
                    backend.start()
                console.print("[green]✓[/] Service installed and started")
            else:
                console.print("[dim]✓ Service already installed[/]")
        except Exception as e:
            console.print(f"[yellow]Service install failed: {e}[/]")
            console.print("[dim]You can install manually: dictare service install[/]")

        console.print()
        console.print("[bold green]Setup complete![/]")
        console.print()
        console.print("  Launch an agent:  [cyan]dictare agent my-first-session[/]")
        console.print("  Start tray icon:  [cyan]dictare tray start[/]")
        console.print()
        console.print("[dim]Runtime lifecycle:[/] dictare upgrade | dictare rollback | dictare repair")
