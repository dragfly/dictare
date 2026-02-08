"""Miscellaneous CLI commands: cmd, backends, init, python env check."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from voxtype.cli._helpers import console
from voxtype.config import create_default_config, get_config_path


def register(app: typer.Typer) -> None:
    """Register misc commands on the main app."""

    @app.command()
    def init() -> None:
        """Create default configuration file."""
        config_path = get_config_path()

        if config_path.exists():
            if not typer.confirm(f"Config file already exists at {config_path}. Overwrite?"):
                raise typer.Abort()

        created_path = create_default_config()
        console.print(f"[green]Created config file:[/] {created_path}")
        console.print("\nEdit this file to customize settings:")
        console.print(f"  [cyan]{created_path}[/]")

    @app.command()
    def cmd(
        ctx: typer.Context,
        command: Annotated[str | None, typer.Argument(help="Command to send (e.g., toggle-listening)")] = None,
    ) -> None:
        """Send a command to a running voxtype instance.

        Used by external tools (like Karabiner-Elements) to control voxtype.

        Available commands:
            toggle-listening, listening-on, listening-off,
            toggle-mode, project-next, project-prev,
            discard, repeat

        Example:
            voxtype cmd toggle-listening
            voxtype cmd project-next
        """
        if command is None:
            import click

            click.echo(ctx.get_help())
            raise typer.Exit(0)

        import socket

        from voxtype.utils.platform import get_socket_dir

        socket_path = str(get_socket_dir() / "control.sock")

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(socket_path)
            sock.send(command.encode())
            sock.close()
            # Silent success for scripting
        except FileNotFoundError:
            console.print("[red]voxtype is not running (socket not found)[/]")
            console.print("[dim]Start voxtype first: voxtype listen[/]")
            raise typer.Exit(1)
        except ConnectionRefusedError:
            console.print("[red]voxtype is not accepting commands[/]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
            raise typer.Exit(1)

    @app.command()
    def backends() -> None:
        """List available device input backends.

        Shows which backends are available on this system for
        handling dedicated input devices (presenter remotes, macro pads).
        """
        from rich.table import Table

        from voxtype.input.backends import get_available_backends

        available = get_available_backends()

        if not available:
            from voxtype.utils.install_info import get_feature_install_message

            console.print("[yellow]No device backends available[/]")
            console.print()
            console.print("[dim]Install dependencies:[/]")
            console.print(f"  macOS: {get_feature_install_message('hidapi').strip()} or brew install --cask karabiner-elements")
            console.print(f"  Linux: {get_feature_install_message('evdev').strip()}")
            raise typer.Exit(1)

        table = Table(title="Device Backends", show_header=True, header_style="bold", expand=False)
        table.add_column("Backend", style="cyan")
        table.add_column("Grab", justify="center")
        table.add_column("Platform")
        table.add_column("Status", justify="center")

        backend_info = {
            "evdev": ("Linux", "Native evdev with exclusive grab"),
            "hidapi": ("All", "Direct HID access, no grab"),
            "karabiner": ("macOS", "Karabiner-Elements with exclusive grab"),
        }

        for name in ["evdev", "karabiner", "hidapi"]:
            platform, desc = backend_info.get(name, ("?", "?"))
            is_available = name in available

            if is_available:
                # Get grab support
                if name == "evdev":
                    from voxtype.input.backends.evdev_backend import EvdevBackend

                    grab = "[green]✓[/]" if EvdevBackend().supports_grab else "[dim]—[/]"
                elif name == "karabiner":
                    from voxtype.input.backends.karabiner_backend import KarabinerBackend

                    grab = "[green]✓[/]" if KarabinerBackend().supports_grab else "[dim]—[/]"
                else:
                    from voxtype.input.backends.hidapi_backend import HIDAPIBackend

                    grab = "[green]✓[/]" if HIDAPIBackend().supports_grab else "[dim]—[/]"

                status = "[green]Available[/]"
            else:
                grab = "[dim]—[/]"
                status = "[dim]Not installed[/]"

            table.add_row(name, grab, platform, status)

        console.print(table)
        console.print()
        console.print("[dim]Grab = exclusive device access (recommended for presenter remotes)[/]")


def check_python_environment() -> None:
    """Check if running in the correct Python environment."""
    import os

    # Expected Python version for uv tool installation
    expected_major = 3
    expected_minor = 11

    major, minor = sys.version_info[:2]

    # If running with wrong Python version, likely a PATH/shim issue
    if major != expected_major or minor != expected_minor:
        # Check if this looks like a pyenv shim issue
        executable = sys.executable
        is_pyenv_shim = ".pyenv" in executable
        is_uv_run = "UV_" in "".join(os.environ.keys()) or ".venv" in executable

        if is_pyenv_shim or is_uv_run:
            from rich.console import Console
            from rich.panel import Panel

            err_console = Console(
                stderr=True,
                force_terminal=None,
                force_interactive=None,
                legacy_windows=False,
                safe_box=True,
            )

            if is_pyenv_shim:
                msg = (
                    f"[yellow]⚠ voxtype is running with Python {major}.{minor} "
                    "via pyenv shim[/]\n\n"
                    f"voxtype was installed with Python {expected_major}.{expected_minor} "
                    "but pyenv is intercepting the command.\n\n"
                    "[bold]Quick fix:[/]\n"
                    "  [cyan]~/.local/bin/voxtype[/]  (use full path)\n\n"
                    "[bold]Permanent fix:[/]\n"
                    "  Move [cyan]~/.local/bin[/] AFTER pyenv init in your shell config,\n"
                    "  so uv tools take precedence over pyenv shims.\n\n"
                    "[dim]This is a PATH ordering issue, not a voxtype bug.[/]"
                )
            else:
                msg = (
                    f"[yellow]⚠ voxtype is running with Python {major}.{minor}[/]\n\n"
                    f"voxtype was installed with Python {expected_major}.{expected_minor}.\n"
                    "It looks like [cyan]uv run[/] is being used instead of the installed binary.\n\n"
                    "[bold]Fix:[/]\n"
                    "  Remove any [cyan]voxtype[/] alias from your shell config,\n"
                    "  or use [cyan]~/.local/bin/voxtype[/] directly."
                )

            err_console.print(Panel(msg, title="Python Environment Issue", border_style="yellow", expand=False))
