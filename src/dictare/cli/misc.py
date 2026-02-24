"""Miscellaneous CLI utilities."""

from __future__ import annotations

import sys

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
                    f"[yellow]⚠ dictare is running with Python {major}.{minor} "
                    "via pyenv shim[/]\n\n"
                    f"dictare was installed with Python {expected_major}.{expected_minor} "
                    "but pyenv is intercepting the command.\n\n"
                    "[bold]Quick fix:[/]\n"
                    "  [cyan]~/.local/bin/dictare[/]  (use full path)\n\n"
                    "[bold]Permanent fix:[/]\n"
                    "  Move [cyan]~/.local/bin[/] AFTER pyenv init in your shell config,\n"
                    "  so uv tools take precedence over pyenv shims.\n\n"
                    "[dim]This is a PATH ordering issue, not a dictare bug.[/]"
                )
            else:
                msg = (
                    f"[yellow]⚠ dictare is running with Python {major}.{minor}[/]\n\n"
                    f"dictare was installed with Python {expected_major}.{expected_minor}.\n"
                    "It looks like [cyan]uv run[/] is being used instead of the installed binary.\n\n"
                    "[bold]Fix:[/]\n"
                    "  Remove any [cyan]dictare[/] alias from your shell config,\n"
                    "  or use [cyan]~/.local/bin/dictare[/] directly."
                )

            err_console.print(Panel(msg, title="Python Environment Issue", border_style="yellow", expand=False))
