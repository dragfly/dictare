"""Shell completion management."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from voxtype.cli._helpers import console

app = typer.Typer(help="Manage shell completion.", no_args_is_help=True)

# Shell completion paths by shell type
COMPLETION_PATHS = {
    "bash": "~/.bash_completion.d/voxtype.bash",
    "zsh": "~/.zfunc/_voxtype",
    "fish": "~/.config/fish/completions/voxtype.fish",
}


def _get_shell() -> str:
    """Detect current shell."""
    import os

    shell_path = os.environ.get("SHELL", "")
    if "zsh" in shell_path:
        return "zsh"
    elif "fish" in shell_path:
        return "fish"
    return "bash"


def _get_completion_script(shell: str) -> str:
    """Generate completion script for shell."""
    import typer.completion

    # Map shell names to typer's expected format
    shell_map = {
        "bash": "bash",
        "zsh": "zsh",
        "fish": "fish",
    }

    if shell not in shell_map:
        return ""

    # Use typer's built-in completion script generation
    return typer.completion.get_completion_script(
        prog_name="voxtype",
        complete_var="_VOXTYPE_COMPLETE",
        shell=shell_map[shell],
    )


@app.command("install")
def completion_install(
    shell: Annotated[str | None, typer.Argument(help="Shell type (bash/zsh/fish)")] = None,
) -> None:
    """Install shell completion."""
    shell = shell or _get_shell()

    if shell not in COMPLETION_PATHS:
        console.print(f"[red]Unsupported shell: {shell}[/]")
        console.print("Supported: bash, zsh, fish")
        raise typer.Exit(1)

    script = _get_completion_script(shell)
    if not script or "not supported" in script.lower():
        console.print(f"[red]Could not generate completion script for {shell}[/]")
        raise typer.Exit(1)

    # Expand path and create parent dirs
    path = Path(COMPLETION_PATHS[shell]).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write completion script
    path.write_text(script)
    console.print(f"[green]Installed completion to {path}[/]")

    # Shell-specific instructions
    if shell == "zsh":
        console.print("\nAdd to ~/.zshrc if not already present:")
        console.print("  [dim]fpath=(~/.zfunc $fpath)[/]")
        console.print("  [dim]autoload -Uz compinit && compinit[/]")
    elif shell == "bash":
        console.print("\nAdd to ~/.bashrc if not already present:")
        console.print(f"  [dim]source {path}[/]")
    elif shell == "fish":
        console.print("\n[green]Fish will load it automatically.[/]")


@app.command("show")
def completion_show(
    shell: Annotated[str | None, typer.Argument(help="Shell type (bash/zsh/fish)")] = None,
) -> None:
    """Show completion script (for manual installation)."""
    shell = shell or _get_shell()
    script = _get_completion_script(shell)

    if not script or "not supported" in script.lower():
        console.print(f"[red]Could not generate completion script for {shell}[/]")
        raise typer.Exit(1)

    print(script)


@app.command("remove")
def completion_remove(
    shell: Annotated[str | None, typer.Argument(help="Shell type (bash/zsh/fish)")] = None,
) -> None:
    """Remove installed shell completion."""
    shell = shell or _get_shell()

    if shell not in COMPLETION_PATHS:
        console.print(f"[red]Unsupported shell: {shell}[/]")
        raise typer.Exit(1)

    path = Path(COMPLETION_PATHS[shell]).expanduser()

    if path.exists():
        path.unlink()
        console.print(f"[green]Removed {path}[/]")
    else:
        console.print(f"[yellow]No completion file found at {path}[/]")
