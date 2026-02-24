"""Model management commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from dictare.cli._helpers import console
from dictare.config import load_config

app = typer.Typer(help="Manage TTS/STT models.", no_args_is_help=True)

_MODEL_REGISTRY: dict | None = None


def _load_model_registry() -> dict:
    """Load model registry from JSON file."""
    import json
    from pathlib import Path

    models_file = Path(__file__).parent.parent / "models.json"
    if models_file.exists():
        with open(models_file) as f:
            return json.load(f)
    return {}


def _get_model_registry() -> dict:
    """Get model registry (lazy loaded)."""
    global _MODEL_REGISTRY
    if _MODEL_REGISTRY is None:
        _MODEL_REGISTRY = _load_model_registry()
    return _MODEL_REGISTRY


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    else:
        return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"


def _get_configured_models(config=None) -> dict[str, str]:
    """Get model names that are configured to be used.

    Returns:
        Dict mapping model registry key to usage type (stt, realtime, tts).
    """
    if config is None:
        config = load_config()

    configured: dict[str, str] = {}
    registry = _get_model_registry()

    # STT model: map config value to registry key
    # Parakeet: "parakeet-v3" -> "parakeet-v3"
    # Whisper:  "large-v3-turbo" -> "whisper-large-v3-turbo"
    stt_model = config.stt.model
    if stt_model in registry:
        configured[stt_model] = "stt"
    else:
        stt_key = f"whisper-{stt_model}"
        if stt_key in registry:
            configured[stt_key] = "stt"

    # TTS capability: match by key or venv field
    # e.g., "coqui" -> "coqui-xtts-v2" (via venv field)
    # e.g., "piper" -> "piper" (direct key match)
    tts_engine = config.tts.engine
    if tts_engine in registry and registry[tts_engine]["type"] == "tts":
        configured[tts_engine] = "tts"
    else:
        for name, info in registry.items():
            if info.get("type") == "tts" and info.get("venv") == tts_engine:
                configured[name] = "tts"
                break

    return configured


def ensure_required_models(config=None) -> bool:
    """Ensure required models are cached, auto-downloading if missing.

    Args:
        config: Config object (loaded if None)

    Returns:
        True if all required models are available, False if download failed.
    """
    from dictare.utils.hf_download import is_repo_cached

    if config is None:
        config = load_config()

    configured = _get_configured_models(config)
    registry = _get_model_registry()
    missing = []

    for name in configured.keys():
        if name in registry:
            info = registry[name]
            if not info.get("repo"):
                continue
            check_file = info.get("check_file", "config.json")
            if not is_repo_cached(info["repo"], check_file):
                missing.append(name)

    if not missing:
        return True

    # Auto-download missing models
    from huggingface_hub import snapshot_download

    from dictare.utils.hf_download import download_with_progress

    console.print(f"[bold]Downloading {len(missing)} missing model(s)...[/]\n")

    for name in missing:
        info = registry[name]
        repo: str = info["repo"]

        console.print(f"[bold]{name}[/] ({info['description']})")

        def _download(r: str = repo) -> str:
            return snapshot_download(r)

        try:
            download_with_progress(
                repo,
                _download,
                fallback_size_gb=info["size_gb"],
            )
            console.print(f"[green]✓ {name} downloaded[/]\n")
        except Exception as e:
            console.print(f"[red]✗ {name} failed: {e}[/]\n")
            console.print("[bold]You can retry with:[/]")
            console.print(f"  [cyan]dictare models pull {name}[/]")
            return False

    return True


def _show_models_list(config=None) -> None:
    """Show models list with configured status highlighting.

    - Green: configured AND cached
    - Red: configured but NOT cached
    - Normal: not configured
    """
    from dictare.utils.hf_download import get_cache_size, is_repo_cached

    if config is None:
        config = load_config()

    configured = _get_configured_models(config)

    table = Table(
        title="Models",
        show_header=True,
        header_style="bold",
        expand=False,
    )
    table.add_column("Model", no_wrap=True)
    table.add_column("Type", width=4)
    table.add_column("Use", width=12)
    table.add_column("Status", justify="center")
    table.add_column("Size", justify="right")

    for name, info in _get_model_registry().items():
        # Skip builtins (no repo to check)
        if info.get("builtin"):
            continue
        repo = info.get("repo")
        if not repo:
            continue
        model_type = info["type"].upper()
        usage = configured.get(name, "")

        # Check if cached
        check_file = info.get("check_file", "config.json")
        cached = is_repo_cached(repo, check_file)

        # Determine colors based on configured + cached state
        if usage:
            if cached:
                # Configured and cached = green
                name_style = "[green]"
                status = "[green]cached[/]"
                use_str = f"[green]{usage}[/]"
            else:
                # Configured but not cached = red
                name_style = "[red]"
                status = "[red]MISSING[/]"
                use_str = f"[red]{usage}[/]"
        else:
            # Not configured = normal/dim
            name_style = "[dim]"
            status = "[dim]cached[/]" if cached else "[dim]—[/]"
            use_str = ""

        # Size
        if cached:
            cache_size = get_cache_size(repo)
            size_str = _format_size(cache_size) if cache_size > 0 else f"~{info['size_gb']:.1f} GB"
        else:
            size_str = f"~{info['size_gb']:.1f} GB"

        table.add_row(
            f"{name_style}{name}[/]",
            model_type,
            use_str,
            status,
            size_str,
        )

    console.print(table)


@app.command("list")
def models_list() -> None:
    """List available models and their cache status.

    Shows STT (Whisper) and TTS models with download status.
    Configured models shown in green (cached) or red (missing).
    """
    config = load_config()
    _show_models_list(config)

    # Show configured TTS engine (system engines aren't in the model registry)
    tts_engine = config.tts.engine
    if tts_engine in ("espeak", "say"):
        from dictare.tts import get_cached_tts_engine

        try:
            tts = get_cached_tts_engine(config.tts)
            available = tts.is_available()
        except ValueError:
            available = False
        status = "[green]available[/]" if available else "[red]not found[/]"
        console.print(f"\n[bold]TTS engine:[/] {tts_engine} ({status})")
    else:
        console.print(f"\n[bold]TTS engine:[/] {tts_engine} (neural model)")

    console.print()
    console.print("[dim]Pull:   dictare models pull <model>[/]")
    console.print("[dim]Remove: dictare models rm <model>[/]")


@app.command("pull")
def models_pull(
    ctx: typer.Context,
    model: Annotated[str | None, typer.Argument(help="Model name to download")] = None,
) -> None:
    """Download a model.

    Examples:
        dictare models pull whisper-large-v3-turbo
        dictare models pull vyvotts-4bit
    """
    if model is None:
        import click

        click.echo(ctx.get_help())
        console.print("\n[bold]Available models:[/]")
        for name in _get_model_registry():
            console.print(f"  {name}")
        raise typer.Exit(0)

    if model not in _get_model_registry():
        console.print(f"[red]Unknown model: {model}[/]")
        console.print("[dim]Run 'dictare models list' to see available models.[/]")
        raise typer.Exit(1)

    info = _get_model_registry()[model]
    repo = info.get("repo")
    if not repo:
        console.print(f"[yellow]Model '{model}' is a builtin — nothing to download[/]")
        raise typer.Exit(0)

    from huggingface_hub import snapshot_download

    from dictare.utils.hf_download import download_with_progress, is_repo_cached

    check_file = info.get("check_file", "config.json")
    if is_repo_cached(repo, check_file):
        console.print(f"[green]Model '{model}' is already cached[/]")
        raise typer.Exit(0)

    console.print(f"[bold]Downloading {model}...[/]")

    try:
        download_with_progress(
            repo,
            lambda: snapshot_download(repo),
            fallback_size_gb=info["size_gb"],
        )
        console.print(f"[green]Model '{model}' downloaded successfully[/]")
    except Exception as e:
        console.print(f"[red]Download failed: {e}[/]")
        raise typer.Exit(1)


@app.command("rm")
def models_rm(
    ctx: typer.Context,
    model: Annotated[str | None, typer.Argument(help="Model name to clear (or 'all')")] = None,
) -> None:
    """Remove cached model(s).

    Examples:
        dictare models rm vyvotts-4bit
        dictare models rm all
    """
    import shutil

    if model is None:
        import click

        click.echo(ctx.get_help())
        raise typer.Exit(0)

    from dictare.utils.hf_download import get_hf_cache_dir

    if model == "all":
        if not typer.confirm("Clear ALL cached models?"):
            raise typer.Abort()

        cleared = 0
        for name, info in _get_model_registry().items():
            if not info.get("repo"):
                continue
            cache_dir = get_hf_cache_dir(info["repo"])
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
                console.print(f"  Cleared {name}")
                cleared += 1

        if cleared == 0:
            console.print("[yellow]No cached models found[/]")
        else:
            console.print(f"[green]Cleared {cleared} model(s)[/]")
        return

    if model not in _get_model_registry():
        console.print(f"[red]Unknown model: {model}[/]")
        console.print("[dim]Run 'dictare models list' to see available models.[/]")
        raise typer.Exit(1)

    info = _get_model_registry()[model]
    repo = info.get("repo")
    if not repo:
        console.print(f"[yellow]Model '{model}' is a builtin — nothing to remove[/]")
        raise typer.Exit(0)
    cache_dir = get_hf_cache_dir(repo)

    if not cache_dir.exists():
        console.print(f"[yellow]Model '{model}' is not cached[/]")
        raise typer.Exit(0)

    shutil.rmtree(cache_dir)
    console.print(f"[green]Cleared '{model}'[/]")
