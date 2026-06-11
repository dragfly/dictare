"""Dictare management routes: settings, system, hotkey, permissions, audio, web UI.

Registered on the FastAPI app by OpenVIPServer._create_app().
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

if TYPE_CHECKING:
    from dictare.core.http_server import OpenVIPServer

logger = logging.getLogger(__name__)


def register_settings_routes(app: FastAPI, server: OpenVIPServer) -> None:
    """Register settings, system, and web UI endpoints on *app*."""

    @app.get("/api/system")
    async def get_system_info():
        """Return system-level info (platform, launch at login state)."""
        import sys as _sys
        info: dict[str, object] = {"platform": _sys.platform}
        if _sys.platform == "darwin":
            from dictare.daemon.launchd import launch_at_login_enabled
            info["launch_at_login"] = launch_at_login_enabled()
        else:
            info["launch_at_login"] = None
        return info

    @app.post("/api/system")
    async def update_system(request: Request):
        """Update system-level settings (e.g. launch at login)."""
        import sys as _sys
        body = await request.json()
        if _sys.platform == "darwin" and "launch_at_login" in body:
            from dictare.daemon.launchd import (
                disable_launch_at_login,
                enable_launch_at_login,
            )
            await asyncio.to_thread(
                enable_launch_at_login if body["launch_at_login"] else disable_launch_at_login
            )
        return {"ok": True}

    @app.get("/api/hotkey/status")
    async def get_hotkey_status():
        """Return CGEventTap status (macOS only)."""
        import sys as _sys
        if _sys.platform != "darwin":
            return {"status": "unsupported"}
        from dictare.hotkey.runtime_status import read_runtime_status

        runtime = read_runtime_status()
        if runtime is not None:
            return {
                "status": runtime.get("status", "unknown"),
                "active_provider": runtime.get("active_provider", "none"),
                "capture_healthy": runtime.get("capture_healthy", False),
            }
        status_file = Path.home() / ".dictare" / "hotkey_status"
        status = status_file.read_text().strip() if status_file.exists() else "unknown"
        return {"status": status}

    @app.post("/api/hotkey/fix")
    async def fix_hotkey():
        """Open System Settings → Input Monitoring (macOS only)."""
        import subprocess
        import sys as _sys
        if _sys.platform == "darwin":
            subprocess.Popen([
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
            ])
        return {"ok": True}

    @app.get("/api/permissions/doctor")
    async def permission_doctor_status():
        """Return consolidated permission + runtime capture status."""
        import sys as _sys

        if _sys.platform != "darwin":
            return {"platform": _sys.platform, "status": "unsupported"}

        from dictare.platform.permission_doctor import PermissionDoctor, status_to_dict

        doctor = PermissionDoctor()
        return {"platform": _sys.platform, "status": "ok", **status_to_dict(doctor.get_status())}

    @app.post("/api/permissions/doctor/open")
    async def permission_doctor_open(request: Request):
        """Open the requested System Settings pane."""
        import sys as _sys

        if _sys.platform != "darwin":
            return {"ok": False, "error": "unsupported"}

        body = await request.json()
        target = str(body.get("target", "input_monitoring"))
        if target not in ("input_monitoring", "accessibility", "microphone"):
            raise HTTPException(status_code=400, detail="Invalid target")

        from dictare.platform.permission_doctor import PermissionDoctor

        PermissionDoctor().open_settings(target)  # type: ignore[arg-type]
        return {"ok": True}

    @app.post("/api/permissions/doctor/probe")
    async def permission_doctor_probe(request: Request):
        """Run runtime hotkey probe; user must press the hotkey during timeout."""
        import sys as _sys

        if _sys.platform != "darwin":
            return {"ok": False, "error": "unsupported"}

        body = await request.json()
        timeout = float(body.get("timeout", 8.0))

        from dictare.platform.permission_doctor import PermissionDoctor

        return await asyncio.to_thread(
            PermissionDoctor().run_probe,
            timeout_s=timeout,
        )

    @app.get("/api/audio/devices")
    async def list_audio_devices():
        """List available audio input and output devices."""
        from dictare.audio.capture import AudioCapture

        return {
            "input": AudioCapture.list_devices(),
            "output": AudioCapture.list_output_devices(),
            "default_input": AudioCapture.get_default_device(),
            "default_output": AudioCapture.get_default_output_device(),
        }

    @app.post("/api/audio/device")
    async def set_audio_device(request: Request):
        """Switch audio input or output device instantly (no engine restart).

        Body: {"type": "input"|"output", "device": "DeviceName" or ""}
        Empty string means "use system default".
        """
        from dictare.config import delete_config_value, set_config_value

        body = await request.json()
        dev_type = body.get("type", "")
        device = body.get("device", "")

        if dev_type not in ("input", "output"):
            raise HTTPException(status_code=400, detail="type must be 'input' or 'output'")

        config_key = f"audio.{dev_type}_device"
        if device:
            set_config_value(config_key, device)
        else:
            delete_config_value(config_key)

        if dev_type == "input":
            server.engine.reset_audio_input()
        else:
            server.engine.reset_audio_output(device)

        server.notify_status_change()
        return {"status": "ok"}

    # ----- Settings UI -----

    _ui_dist = Path(__file__).parent.parent / "ui" / "dist"

    @app.middleware("http")
    async def ui_cache_control(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Cache-control for UI static assets.

        SvelteKit hashes JS/CSS in _app/immutable/ → cache forever.
        index.html and other top-level files → never cache (prevents stale UI after upgrade).
        """
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/ui/"):
            if "/immutable/" in path:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.get("/settings")
    async def settings_redirect():
        """Redirect to Settings SPA."""
        return RedirectResponse(url="/ui/")

    @app.get("/ui")
    async def ui_redirect():
        """Redirect /ui to /ui/."""
        return RedirectResponse(url="/ui/")

    app.mount(
        "/ui",
        StaticFiles(directory=str(_ui_dist), html=True),
        name="ui",
    )

    @app.get("/api/settings/schema")
    async def settings_schema():
        """Return JSON Schema, current values, field metadata, plus TOML sections,
        shortcuts, and presets — everything the UI needs in ONE fetch."""
        from dictare import __version__
        from dictare.audio.capture import AudioCapture
        from dictare.config import Config, list_config_keys, load_config, load_raw_values
        from dictare.core.toml_sections import SUPPORTED_SECTIONS, serialize_section

        config = load_config()
        values = config.model_dump()
        raw = load_raw_values()

        # String fields not explicitly in TOML → "" (means "use default").
        # Bool/number fields keep their Pydantic-resolved defaults.
        config_keys = list(list_config_keys())
        for key, type_name, _default, _desc, _env_var in config_keys:
            if type_name == "str" and key not in raw:
                parts = key.split(".")
                obj = values
                for p in parts[:-1]:
                    obj = obj[p]
                obj[parts[-1]] = ""

        # TOML sections — serialized fragments for all supported sections
        toml_sections: dict[str, str] = {}
        for section in SUPPORTED_SECTIONS:
            try:
                toml_sections[section] = serialize_section(section, config)
            except KeyError:
                pass

        # Shortcuts
        shortcuts = [
            {"keys": str(s.get("keys", "")), "command": str(s.get("command", ""))}
            for s in config.keyboard.shortcuts
            if s.get("keys") and s.get("command")
        ]

        # Presets — defaults + backend-driven option lists
        presets: dict[str, dict] = {
            key: {"default": default}
            for key, _type_name, default, _desc, _env_var in config_keys
        }
        try:
            input_devices = AudioCapture.list_devices()
            output_devices = AudioCapture.list_output_devices()
            default_input = AudioCapture.get_default_device()
            default_output = AudioCapture.get_default_output_device()

            if "audio.input_device" in presets:
                presets["audio.input_device"]["values"] = [
                    {"value": d["name"], "label": d["name"]} for d in input_devices
                ]
                if default_input:
                    presets["audio.input_device"]["default"] = default_input.get("name", "")

            if "audio.output_device" in presets:
                presets["audio.output_device"]["values"] = [
                    {"value": d["name"], "label": d["name"]} for d in output_devices
                ]
                if default_output:
                    presets["audio.output_device"]["default"] = default_output.get("name", "")
        except Exception:
            pass

        return {
            "schema": Config.model_json_schema(),
            "values": values,
            "keys": [
                {
                    "key": key,
                    "type": type_name,
                    "default": default,
                    "description": desc,
                    "env_var": env_var,
                }
                for key, type_name, default, desc, env_var in config_keys
            ],
            "version": __version__,
            "toml_sections": toml_sections,
            "shortcuts": shortcuts,
            "presets": presets,
        }

    @app.get("/api/settings/presets")
    async def settings_presets():
        """Return default values and backend-defined option lists for settings fields.

        Response shape: {key: {default, values?}}
        - default: the value the backend uses when the field is not set
        - values: only present for backend-driven fields (e.g. audio devices);
                  list of {value, label} options available at runtime

        Used by the UI to show "Default (x)" labels and populate backend-driven dropdowns.
        """
        from dictare.audio.capture import AudioCapture
        from dictare.config import list_config_keys

        result: dict[str, dict] = {
            key: {"default": default}
            for key, _type_name, default, _desc, _env_var in list_config_keys()
        }

        # Enrich audio device fields with runtime-available options
        try:
            input_devices = AudioCapture.list_devices()
            output_devices = AudioCapture.list_output_devices()
            default_input = AudioCapture.get_default_device()
            default_output = AudioCapture.get_default_output_device()

            if "audio.input_device" in result:
                result["audio.input_device"]["values"] = [
                    {"value": d["name"], "label": d["name"]} for d in input_devices
                ]
                if default_input:
                    result["audio.input_device"]["default"] = default_input.get("name", "")

            if "audio.output_device" in result:
                result["audio.output_device"]["values"] = [
                    {"value": d["name"], "label": d["name"]} for d in output_devices
                ]
                if default_output:
                    result["audio.output_device"]["default"] = default_output.get("name", "")
        except Exception:
            pass

        return result

    @app.post("/api/settings")
    async def update_setting(request: Request):
        """Update a single config value. Send value="" to reset to Pydantic default."""
        from pydantic import ValidationError

        from dictare.config import (
            delete_config_value,
            get_config_value,
            load_config,
            set_config_value,
        )

        body = await request.json()
        key = body.get("key", "")
        value = body.get("value")
        if not key:
            raise HTTPException(status_code=400, detail="Missing 'key'")
        if value is None:
            raise HTTPException(status_code=400, detail="Missing 'value'")
        try:
            if value == "":
                delete_config_value(key)
            else:
                set_config_value(key, str(value))
            config = load_config()
            current = get_config_value(key, config)
            logger.info("settings.change key=%s value=%r", key, current)
            return {"status": "ok", "key": key, "value": current}
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ValueError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/settings/shortcuts")
    async def get_shortcuts():
        """Return keyboard shortcuts as a JSON list."""
        from dictare.config import load_config

        config = load_config()
        shortcuts = [
            {"keys": str(s.get("keys", "")), "command": str(s.get("command", ""))}
            for s in config.keyboard.shortcuts
            if s.get("keys") and s.get("command")
        ]
        return {"shortcuts": shortcuts}

    @app.post("/api/settings/shortcuts")
    async def save_shortcuts(request: Request):
        """Save keyboard shortcuts from a JSON list."""
        from pydantic import ValidationError

        from dictare.config import get_config_path, load_config
        from dictare.core.toml_sections import apply_section, shortcuts_to_toml

        body = await request.json()
        shortcuts: list[dict[str, str]] = body.get("shortcuts", [])
        for s in shortcuts:
            if not s.get("keys") or not s.get("command"):
                raise HTTPException(
                    status_code=400, detail="Each shortcut must have 'keys' and 'command'"
                )
        toml_content = shortcuts_to_toml(shortcuts)
        try:
            apply_section("keyboard.shortcuts", toml_content, get_config_path())
            load_config()
        except (ValueError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"status": "ok"}

    @app.get("/api/settings/toml-section/{section}")
    async def get_toml_section(section: str):
        """Return the current TOML fragment for a complex config section."""
        from dictare.config import load_config
        from dictare.core.toml_sections import serialize_section

        config = load_config()
        try:
            content = serialize_section(section, config)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown section: {section}")
        return {"section": section, "content": content}

    @app.post("/api/settings/toml-section/{section}")
    async def update_toml_section(section: str, request: Request):
        """Validate and save a TOML section submitted from the UI editor."""
        from pydantic import ValidationError

        from dictare.config import get_config_path, load_config
        from dictare.core.toml_sections import apply_section

        body = await request.json()
        content = body.get("content", "")
        if not content.strip():
            raise HTTPException(status_code=400, detail="Empty content")
        try:
            apply_section(section, content, get_config_path())
            load_config()  # re-validate after save
            logger.info("settings.change section=%s (toml)", section)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown section: {section}")
        except (ValueError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"status": "ok", "section": section}
