"""dictare status — engine and system health overview."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from dictare.cli._helpers import console

def _format_uptime(seconds: float) -> str:
    """Format seconds into human-readable uptime."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining_min = minutes % 60
    return f"{hours}h {remaining_min}m"

def _status_icon(available: bool) -> str:
    """Rich markup for OK/MISSING."""
    if available:
        return "[green]OK[/]"
    return "[red]MISSING[/]"

def _render_online(status_data: dict) -> None:
    """Render status when engine is running."""
    from dictare import __version__

    platform = status_data.get("platform", {})
    stt = platform.get("stt", {})
    tts = platform.get("tts", {})
    output = platform.get("output", {})
    uptime = platform.get("uptime_seconds", 0)

    console.print(f"\n[bold]Dictare[/] v{platform.get('version', __version__)}\n")

    # Engine summary
    mode = platform.get("mode", "?")
    console.print(f"  Engine     [green]running[/] ({mode} mode, {_format_uptime(uptime)})")
    console.print(f"  State      {platform.get('state', '?')}")
    console.print(f"  STT        {stt.get('model_name', '?')} on {stt.get('device', '?')}")

    tts_name = tts.get("engine", "?")
    tts_status = "[green]active[/]" if tts.get("available") else "[red]unavailable[/]"
    console.print(f"  TTS        {tts_name} ({tts_status})")

    agents = output.get("available_agents", [])
    current = output.get("current_agent", "")
    if agents:
        parts = []
        for a in agents:
            if a == current:
                parts.append(f"[bold]{a}[/] (active)")
            else:
                parts.append(a)
        console.print(f"  Agents     {', '.join(parts)}")
    else:
        console.print("  Agents     [dim]none connected[/]")

    # Engine availability tables
    engines = platform.get("engines", {})
    _render_engine_table("TTS Engines", engines.get("tts", []))
    _render_engine_table("STT Engines", engines.get("stt", []))

    # Permissions
    perms = platform.get("permissions", {})
    perm_parts = []
    for key, ok in perms.items():
        label = key.replace("_", " ").title()
        perm_parts.append(f"{label} {'[green]OK[/]' if ok else '[red]DENIED[/]'}")

    if perm_parts:
        console.print("\n[bold]System[/]")
        console.print(f"  {' | '.join(perm_parts)}")

    console.print()

def _render_engine_table(title: str, engines: list[dict]) -> None:
    """Render an engine availability table."""
    if not engines:
        return

    console.print(f"\n[bold]{title}[/]")
    for eng in engines:
        name = eng["name"]
        available = eng["available"]
        desc = eng["description"]
        hint = eng.get("install_hint", "")
        configured = eng.get("configured", False)

        icon = _status_icon(available)
        suffix = f"  [dim]{desc}[/]"
        if configured:
            suffix += "  [cyan]*[/]"
        if not available and hint:
            suffix += f"\n{'':14}[yellow]{hint}[/]"

        console.print(f"  {name:12} {icon}{suffix}")

def _render_offline() -> None:
    """Render status when engine is not running."""
    from dictare import __version__
    from dictare.utils.platform import (
        check_all_stt_engines,
        check_all_tts_engines,
        check_dependencies,
    )

    console.print(f"\n[bold]Dictare[/] v{__version__}\n")
    console.print("  Engine     [yellow]offline[/]\n")

    # Load config for configured engine info
    configured_tts = ""
    configured_stt = ""
    try:
        from dictare.config import load_config

        config = load_config()
        configured_tts = config.tts.engine
        configured_stt = config.stt.model
    except Exception:
        pass

    _render_engine_table("TTS Engines", check_all_tts_engines(configured_tts))
    _render_engine_table("STT Engines", check_all_stt_engines(configured_stt))

    # System dependencies
    deps = check_dependencies()
    console.print("\n[bold]System[/]")
    dep_parts = []
    for d in deps:
        label = d.name
        icon = "[green]OK[/]" if d.available else "[red]FAIL[/]"
        dep_parts.append(f"{label} {icon}")
    console.print(f"  {' | '.join(dep_parts)}")
    console.print()

def _get_status_json(online: bool = True) -> dict:
    """Build JSON output for --json mode."""
    if online:
        from openvip import Client

        from dictare.config import load_config

        config = load_config()
        client = Client(
            f"http://{config.server.host}:{config.server.port}",
            timeout=2,
        )
        status = client.get_status()
        return {
            "online": True,
            "openvip": status.openvip,
            "stt": status.stt,
            "tts": status.tts,
            "connected_agents": status.connected_agents,
            "platform": status.platform,
        }
    else:
        from dictare import __version__
        from dictare.utils.platform import (
            check_all_stt_engines,
            check_all_tts_engines,
        )

        configured_tts = ""
        configured_stt = ""
        try:
            from dictare.config import load_config

            config = load_config()
            configured_tts = config.tts.engine
            configured_stt = config.stt.model
        except Exception:
            pass

        return {
            "online": False,
            "version": __version__,
            "engines": {
                "tts": check_all_tts_engines(configured_tts),
                "stt": check_all_stt_engines(configured_stt),
            },
        }

def register(app: typer.Typer) -> None:
    """Register status command on the main app."""

    @app.command()
    def status(
        json_output: Annotated[
            bool,
            typer.Option("--json", help="Output as JSON"),
        ] = False,
    ) -> None:
        """Show engine health and system status."""
        from openvip import Client

        from dictare.config import load_config

        # Try connecting to running engine
        try:
            config = load_config()
            client = Client(
                f"http://{config.server.host}:{config.server.port}",
                timeout=2,
            )
            status_data = client.get_status()
            online = True
        except Exception:
            online = False

        if json_output:
            try:
                data = _get_status_json(online=online)
            except Exception:
                data = _get_status_json(online=False)
            console.print_json(json.dumps(data))
        elif online:
            # Build full dict from Status object
            full = {
                "openvip": status_data.openvip,  # type: ignore[possibly-undefined]
                "stt": status_data.stt,  # type: ignore[possibly-undefined]
                "tts": status_data.tts,  # type: ignore[possibly-undefined]
                "connected_agents": status_data.connected_agents,  # type: ignore[possibly-undefined]
                "platform": status_data.platform,  # type: ignore[possibly-undefined]
            }
            _render_online(full)
        else:
            _render_offline()
