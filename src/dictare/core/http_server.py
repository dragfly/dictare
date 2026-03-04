"""FastAPI HTTP server for OpenVIP (Open Voice Interaction Protocol).

Provides SSE-based agent communication, TTS, status, and control endpoints.
Runs in its own background thread with a dedicated asyncio event loop.

The HTTP adapter translates HTTP requests to method calls on Engine
(protocol commands) and AppController (application commands).
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from dictare import OPENVIP_BASE_PATH, __version__
from dictare.core.openvip_validator import OpenVIPValidationError, validate_message

if TYPE_CHECKING:
    from dictare.app.controller import AppController
    from dictare.core.engine import DictareEngine

logger = logging.getLogger(__name__)

# Protocol commands handled by the engine directly
PROTOCOL_COMMANDS = {"stt.start", "stt.stop", "stt.toggle", "engine.shutdown", "engine.restart", "ping", "hotkey.capture"}

# Seconds to wait for HTTP server thread to exit on stop()
_SERVER_JOIN_TIMEOUT: float = 0.5

# Seconds to keep completed download jobs before cleanup
_JOB_CLEANUP_DELAY: float = 10.0


class OpenVIPServer:
    """FastAPI server implementing OpenVIP protocol endpoints.

    Runs in a background thread with its own asyncio event loop.
    Thread-safe message delivery via asyncio.Queue per agent.

    Endpoints (OpenVIP protocol — mounted at /openvip):
        GET  /openvip/agents/{agent_id}/messages  - SSE stream (connection = registration)
        POST /openvip/agents/{agent_id}/messages  - Send message to agent
        POST /openvip/speech                      - Speech (TTS) request
        GET  /openvip/status                      - Engine status
        GET  /openvip/status/stream               - SSE stream for status changes
        POST /openvip/control                     - Control commands
        GET  /openvip/openapi.json                - OpenVIP protocol spec

    Endpoints (dictare management — mounted at /api):
        GET  /api/speech/voices           - Available TTS voices
        GET  /api/audio/devices           - Audio input/output devices
        GET  /api/settings/schema         - Config schema + current values
        POST /api/settings                - Update a config value
        GET  /api/settings/shortcuts      - Keyboard shortcuts
        POST /api/settings/shortcuts      - Save keyboard shortcuts
        GET  /api/settings/toml-section/* - Read TOML config section
        POST /api/settings/toml-section/* - Save TOML config section
        GET  /api/models                  - STT/TTS model list
        POST /api/models/{id}/pull        - Start model download
        GET  /api/models/pull-progress    - SSE download progress
        GET  /api/capabilities            - Unified capability list
        POST /api/capabilities/{id}/install   - Install capability
        DELETE /api/capabilities/{id}/install - Uninstall capability
        POST /api/capabilities/{id}/select    - Select active capability
        GET  /api/system                  - System info
        POST /api/system                  - Update system settings
        GET  /api/hotkey/status           - Hotkey capture status
        POST /api/hotkey/fix              - Open Input Monitoring settings
        GET  /api/permissions/doctor      - Permission health check
        POST /api/permissions/doctor/open - Open permission settings pane
        POST /api/permissions/doctor/probe - Run runtime hotkey probe

    Root endpoints:
        GET  /health                      - Liveness probe
        GET  /ui                          - Web UI (SPA)
        POST /internal/tts/complete       - TTS worker completion callback
    """

    def __init__(
        self,
        engine: DictareEngine,
        controller: AppController | None = None,
        host: str = "127.0.0.1",
        port: int = 8770,
        auth_tokens: dict[str, str] | None = None,
    ) -> None:
        self._engine = engine
        self._controller = controller
        self._host = host
        self._port = port
        self._auth_tokens: dict[str, str] = auth_tokens or {}

        # Event set when __tts__ agent connects, cleared on disconnect
        self._tts_connected_event = threading.Event()

        # Agent queues: agent_id -> asyncio.Queue
        self._agent_queues: dict[str, asyncio.Queue] = {}
        self._agent_queues_lock = threading.Lock()

        # Status stream subscribers: list of asyncio.Queue
        self._status_queues: list[asyncio.Queue] = []
        self._status_queues_lock = threading.Lock()

        # Model download jobs: model_id -> {status, fraction, downloaded_bytes, total_bytes}
        self._download_jobs: dict[str, dict] = {}
        self._progress_queues: list[asyncio.Queue] = []
        self._progress_queues_lock = threading.Lock()

        # Server thread and event loop
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: Any = None  # uvicorn.Server
        self._running = False
        self._started = threading.Event()
        self._start_error: Exception | None = None  # Set if server failed to start

        # FastAPI app
        self._app = self._create_app()

    def is_tts_connected(self) -> bool:
        """Check if the TTS worker has connected."""
        return self._tts_connected_event.is_set()

    def wait_tts_connected(self, timeout: float = 0.5) -> bool:
        """Wait for TTS worker to connect. Returns True if connected."""
        return self._tts_connected_event.wait(timeout=timeout)

    def _has_permission(self, request: Request, permission: str) -> bool:
        """Check if request carries a valid Bearer token for *permission*."""
        token = self._auth_tokens.get(permission)
        if not token:
            return False
        auth = request.headers.get("authorization", "")
        return auth == f"Bearer {token}"

    def _create_app(self) -> FastAPI:
        """Create FastAPI application with all endpoints."""
        app = FastAPI(
            title="Dictare OpenVIP Server",
            version=__version__,
            docs_url=None,  # Disable docs in production
            redoc_url=None,
        )

        @app.get("/health")
        async def health():
            """Liveness probe — returns 200 when engine is up."""
            return {"status": "ok"}

        @app.get("/openvip/agents/{agent_id}/messages")
        async def sse_agent_messages(agent_id: str, request: Request):
            """SSE endpoint - connection IS the agent registration."""
            from dictare.core.engine import DictareEngine

            # Reject reserved agent IDs unless caller has the right token
            if agent_id in DictareEngine.RESERVED_AGENT_IDS:
                if not self._has_permission(request, "register_tts"):
                    raise HTTPException(
                        status_code=403,
                        detail="Reserved agent ID",
                    )
            # Check for duplicate connection
            with self._agent_queues_lock:
                if agent_id in self._agent_queues:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Agent '{agent_id}' already connected",
                    )
                queue: asyncio.Queue = asyncio.Queue()
                self._agent_queues[agent_id] = queue

            # Create SSE agent and register with engine
            from dictare.agent.sse import SSEAgent

            agent = SSEAgent(agent_id, self)
            self._engine.register_agent(agent)
            is_tts = agent_id == DictareEngine.TTS_AGENT_ID
            if is_tts:
                self._tts_connected_event.set()
            logger.info("SSE agent connected: %s", agent_id)

            async def event_generator():
                try:
                    while True:
                        # Check if client disconnected
                        if await request.is_disconnected():
                            break

                        try:
                            # Wait for message with timeout for keepalive
                            message = await asyncio.wait_for(
                                queue.get(), timeout=30.0
                            )
                            yield {
                                "event": message.get("type", "message"),
                                "data": json.dumps(message, ensure_ascii=False),
                            }
                        except TimeoutError:
                            # Send keepalive comment
                            yield {"comment": "keepalive"}
                finally:
                    # Cleanup on disconnect
                    with self._agent_queues_lock:
                        self._agent_queues.pop(agent_id, None)
                    self._engine.unregister_agent(agent_id)
                    if is_tts:
                        self._tts_connected_event.clear()
                    logger.info("SSE agent disconnected: %s", agent_id)

            return EventSourceResponse(event_generator())

        @app.post("/openvip/agents/{agent_id}/messages")
        async def post_agent_message(agent_id: str, request: Request):
            """Send a message to a connected agent."""
            with self._agent_queues_lock:
                queue = self._agent_queues.get(agent_id)
            if queue is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent '{agent_id}' not connected",
                )
            try:
                body = await request.json()
            except (ValueError, UnicodeDecodeError):
                raise HTTPException(
                    status_code=422,
                    detail="Not OpenVIP v1.0 compliant: invalid JSON body",
                )
            try:
                validate_message(body)
            except OpenVIPValidationError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            queue.put_nowait(body)
            return {"status": "ok"}

        @app.post("/openvip/speech")
        async def speech_request(request: Request):
            """Handle speech (TTS) request."""
            try:
                body = await request.json()
            except (ValueError, UnicodeDecodeError):
                raise HTTPException(
                    status_code=422,
                    detail="Not OpenVIP v1.0 compliant: invalid JSON body",
                )
            try:
                validate_message(body)
            except OpenVIPValidationError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            try:
                result = await asyncio.to_thread(
                    self._engine.handle_speech, body
                )
                if result.get("status") == "error":
                    raise HTTPException(status_code=422, detail=result["error"])
                return result
            except HTTPException:
                raise
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/openvip/speech/stop")
        async def speech_stop():
            """Interrupt the currently playing TTS audio."""
            stopped = await asyncio.to_thread(self._engine.stop_speaking)
            return {"status": "ok", "stopped": stopped}

        @app.post("/api/agents/{agent_id}/focus")
        async def set_agent_focus(agent_id: str, request: Request):
            """Report terminal focus state for an agent."""
            try:
                body = await request.json()
            except (ValueError, UnicodeDecodeError):
                raise HTTPException(status_code=422, detail="Invalid JSON body")
            focused = body.get("focused")
            if not isinstance(focused, bool):
                raise HTTPException(status_code=422, detail="'focused' must be a boolean")
            self._engine.set_agent_focus(agent_id, focused)
            return {"status": "ok"}

        @app.get("/api/speech/voices")
        async def speech_voices():
            """List available voices for the current TTS engine."""
            voices = await asyncio.to_thread(self._engine.list_voices)
            return {
                "engine": self._engine.config.tts.engine,
                "voices": voices,
            }

        @app.post("/internal/tts/complete")
        async def tts_complete(request: Request):
            """Worker signals that a speak() call finished."""
            if not self._has_permission(request, "register_tts"):
                raise HTTPException(status_code=403, detail="Forbidden")
            body = await request.json()
            message_id = body.get("message_id", "")
            ok = body.get("ok", False)
            duration_ms = body.get("duration_ms", 0)
            self._engine.complete_tts(message_id, ok=ok, duration_ms=duration_ms)
            return {"status": "ok"}

        @app.get("/openvip/status")
        async def get_status():
            """Get engine status."""
            return self._engine.get_status()

        @app.get("/openvip/status/stream")
        async def sse_status_stream(request: Request):
            """SSE stream for status changes.

            Pushes a Status object on every state transition.
            Sends keepalive comments every 30s if no events.
            """
            sq: asyncio.Queue = asyncio.Queue()
            with self._status_queues_lock:
                self._status_queues.append(sq)

            # Send current status immediately on connect
            initial = self._engine.get_status()
            await sq.put(initial)

            async def event_generator():
                try:
                    while True:
                        if await request.is_disconnected():
                            break
                        try:
                            status = await asyncio.wait_for(
                                sq.get(), timeout=30.0
                            )
                            yield {
                                "data": json.dumps(
                                    status, ensure_ascii=False, default=str
                                ),
                            }
                        except TimeoutError:
                            yield {"comment": "keepalive"}
                finally:
                    with self._status_queues_lock:
                        try:
                            self._status_queues.remove(sq)
                        except ValueError:
                            pass

            return EventSourceResponse(event_generator())

        @app.post("/openvip/control")
        async def control_command(request: Request):
            """Handle control commands.

            Routes protocol commands (stt.*, engine.shutdown, ping) to the
            engine and application commands to the controller.
            """
            body = await request.json()
            command = body.get("command", "")
            try:
                # Protocol commands → engine
                if command in PROTOCOL_COMMANDS:
                    result = await asyncio.to_thread(
                        self._engine.handle_protocol_command, body
                    )
                    return result

                # App commands → controller
                if self._controller is not None:
                    result = await asyncio.to_thread(
                        self._controller._handle_app_command, body
                    )
                    return result

                return {"status": "error", "error": f"Unknown command: {command}"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/openvip/openapi.json")
        async def openvip_spec():
            """Serve the OpenVIP protocol spec for API discovery."""
            from starlette.responses import FileResponse
            spec = _Path(__file__).parent.parent / "resources" / "openvip-openapi.json"
            if spec.exists():
                return FileResponse(str(spec), media_type="application/json")
            raise HTTPException(status_code=404, detail="OpenVIP spec not available")

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
                raise HTTPException(status_code=422, detail="Invalid target")

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

        # ----- Settings UI -----

        from pathlib import Path as _Path

        from starlette.responses import RedirectResponse
        from starlette.staticfiles import StaticFiles

        _ui_dist = _Path(__file__).parent.parent / "ui" / "dist"

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
                raise HTTPException(status_code=422, detail=str(e))

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
                        status_code=422, detail="Each shortcut must have 'keys' and 'command'"
                    )
            toml_content = shortcuts_to_toml(shortcuts)
            try:
                apply_section("keyboard.shortcuts", toml_content, get_config_path())
                load_config()
            except (ValueError, ValidationError) as e:
                raise HTTPException(status_code=422, detail=str(e))
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
                raise HTTPException(status_code=422, detail=str(e))
            return {"status": "ok", "section": section}

        # ----- Models API -----

        @app.get("/api/models")
        async def models_list_api():
            """List all models with cache and configured status."""
            from dictare.cli.models import _get_configured_models, _get_model_registry
            from dictare.config import load_config
            from dictare.utils.hf_download import get_cache_size, is_repo_cached

            config = load_config()
            registry = _get_model_registry()
            configured = _get_configured_models(config)

            result = []
            for model_id, info in registry.items():
                repo = info.get("repo")
                if not repo:
                    continue  # skip builtins in legacy /models endpoint
                check_file = info.get("check_file", "config.json")
                cached = await asyncio.to_thread(is_repo_cached, repo, check_file)
                cache_size = await asyncio.to_thread(get_cache_size, repo) if cached else 0

                job = self._download_jobs.get(model_id)
                downloading = job is not None and job.get("status") == "downloading"

                result.append({
                    "id": model_id,
                    "type": info["type"],
                    "description": info["description"],
                    "size_gb": info["size_gb"],
                    "cached": cached,
                    "cache_size_bytes": cache_size,
                    "configured": configured.get(model_id, ""),
                    "downloading": downloading,
                    "download_fraction": job.get("fraction") if downloading else None,
                    "downloaded_bytes": job.get("downloaded_bytes", 0) if downloading else 0,
                    "total_bytes": job.get("total_bytes", 0) if downloading else 0,
                })

            return {"models": result}

        @app.post("/api/models/{model_id}/pull")
        async def models_pull_api(model_id: str):
            """Start async download of a model."""
            from dictare.cli.models import _get_model_registry
            from dictare.utils.hf_download import is_repo_cached

            registry = _get_model_registry()
            if model_id not in registry:
                raise HTTPException(status_code=404, detail=f"Unknown model: {model_id}")

            info = registry[model_id]
            repo = info["repo"]
            check_file = info.get("check_file", "config.json")

            if await asyncio.to_thread(is_repo_cached, repo, check_file):
                return {"status": "cached"}

            if model_id in self._download_jobs and self._download_jobs[model_id].get("status") == "downloading":
                return {"status": "downloading"}

            loop = asyncio.get_running_loop()
            t = threading.Thread(
                target=self._run_model_download,
                args=(model_id, info, loop),
                daemon=True,
                name=f"model-dl-{model_id}",
            )
            t.start()
            return {"status": "started"}

        @app.get("/api/models/pull-progress")
        async def models_pull_progress(request: Request):
            """SSE stream for model download progress."""
            pq: asyncio.Queue = asyncio.Queue()
            with self._progress_queues_lock:
                self._progress_queues.append(pq)

            # Send snapshot of all in-progress jobs on connect
            for mid, job in self._download_jobs.items():
                await pq.put({"model_id": mid, **job})

            async def event_generator():
                try:
                    while True:
                        if await request.is_disconnected():
                            break
                        try:
                            event = await asyncio.wait_for(pq.get(), timeout=30.0)
                            yield {"data": json.dumps(event, ensure_ascii=False, default=str)}
                        except TimeoutError:
                            yield {"comment": "keepalive"}
                finally:
                    with self._progress_queues_lock:
                        try:
                            self._progress_queues.remove(pq)
                        except ValueError:
                            pass

            return EventSourceResponse(event_generator())

        # ----- TTS Venv Install/Uninstall API (legacy, kept for compat) -----

        @app.post("/api/tts-engines/{engine}/install")
        async def tts_engine_install(engine: str):
            """Install an isolated TTS venv for an engine."""
            from dictare.tts.venv import VENV_ENGINES

            if engine not in VENV_ENGINES:
                raise HTTPException(
                    status_code=404,
                    detail=f"Unknown venv engine: {engine}. Valid: {', '.join(VENV_ENGINES)}",
                )

            job_id = f"tts-install-{engine}"
            if job_id in self._download_jobs and self._download_jobs[job_id].get("status") == "downloading":
                return {"status": "installing"}

            loop = asyncio.get_running_loop()
            t = threading.Thread(
                target=self._run_tts_install,
                args=(engine, loop),
                daemon=True,
                name=f"tts-install-{engine}",
            )
            t.start()
            return {"status": "started"}

        @app.delete("/api/tts-engines/{engine}/install")
        async def tts_engine_uninstall(engine: str):
            """Remove the isolated TTS venv for an engine."""
            from dictare.tts.venv import VENV_ENGINES, uninstall_venv

            if engine not in VENV_ENGINES:
                raise HTTPException(
                    status_code=404,
                    detail=f"Unknown venv engine: {engine}. Valid: {', '.join(VENV_ENGINES)}",
                )

            await asyncio.to_thread(uninstall_venv, engine)
            return {"status": "ok"}

        # ----- Capabilities API (unified models + engines) -----

        @app.get("/api/capabilities")
        async def capabilities_list():
            """List all STT/TTS capabilities with install and config status."""
            import shutil
            import sys

            from dictare.cli.models import _get_configured_models, _get_model_registry
            from dictare.config import load_config
            from dictare.tts.venv import is_venv_installed
            from dictare.utils.hardware import is_apple_silicon
            from dictare.utils.hf_download import is_repo_cached

            config = load_config()
            registry = _get_model_registry()
            configured = _get_configured_models(config)

            result = []
            for cap_id, info in registry.items():
                cap_type = info["type"]
                builtin = info.get("builtin", False)
                platform_req = info.get("platform")
                venv_name = info.get("venv")
                repo = info.get("repo")
                check_file = info.get("check_file", "config.json")

                # Platform check
                if platform_req == "darwin":
                    platform_ok = sys.platform == "darwin"
                elif platform_req == "apple_silicon":
                    platform_ok = await asyncio.to_thread(is_apple_silicon)
                else:
                    platform_ok = True

                # Venv check
                if venv_name:
                    venv_installed = await asyncio.to_thread(is_venv_installed, venv_name)
                else:
                    venv_installed = True  # no venv needed

                # Model cache check
                if repo:
                    model_cached = await asyncio.to_thread(is_repo_cached, repo, check_file)
                else:
                    model_cached = True  # no model to download

                # Builtin readiness: check binary exists
                if builtin:
                    if cap_id == "say":
                        ready = platform_ok and await asyncio.to_thread(
                            lambda: shutil.which("say") is not None
                        )
                    elif cap_id == "espeak":
                        ready = await asyncio.to_thread(
                            lambda: (
                                shutil.which("espeak-ng") is not None
                                or shutil.which("espeak") is not None
                            )
                        )
                    else:
                        ready = platform_ok
                else:
                    ready = platform_ok and venv_installed and model_cached

                # Download state
                job = self._download_jobs.get(cap_id) or self._download_jobs.get(f"tts-install-{venv_name}")
                downloading = job is not None and job.get("status") == "downloading"

                result.append({
                    "id": cap_id,
                    "type": cap_type,
                    "description": info["description"],
                    "size_gb": info["size_gb"],
                    "platform_ok": platform_ok,
                    "ready": ready,
                    "venv_installed": venv_installed if venv_name else None,
                    "model_cached": model_cached if repo else None,
                    "configured": cap_id in configured,
                    "builtin": builtin,
                    "downloading": downloading,
                    "download_fraction": job.get("fraction") if downloading else None,
                })

            return {"capabilities": result}

        @app.post("/api/capabilities/{cap_id}/install")
        async def capability_install(cap_id: str):
            """Install a capability (venv + model download)."""
            from dictare.cli.models import _get_model_registry
            from dictare.tts.venv import is_venv_installed
            from dictare.utils.hf_download import is_repo_cached

            registry = _get_model_registry()
            if cap_id not in registry:
                raise HTTPException(status_code=404, detail=f"Unknown capability: {cap_id}")

            info = registry[cap_id]
            if info.get("builtin"):
                raise HTTPException(status_code=400, detail="Builtin capability — nothing to install")

            venv_name = info.get("venv")
            repo = info.get("repo")

            # Already fully installed?
            venv_ok = not venv_name or is_venv_installed(venv_name)
            model_ok = not repo or is_repo_cached(repo, info.get("check_file", "config.json"))
            if venv_ok and model_ok:
                return {"status": "ready"}

            # Check for existing job
            if cap_id in self._download_jobs and self._download_jobs[cap_id].get("status") == "downloading":
                return {"status": "installing"}

            loop = asyncio.get_running_loop()
            t = threading.Thread(
                target=self._run_capability_install,
                args=(cap_id, info, loop),
                daemon=True,
                name=f"cap-install-{cap_id}",
            )
            t.start()
            return {"status": "started"}

        @app.delete("/api/capabilities/{cap_id}/install")
        async def capability_uninstall(cap_id: str):
            """Uninstall a capability: removes venv and/or cached model files."""
            import shutil

            from dictare.cli.models import _get_model_registry
            from dictare.tts.venv import VENV_ENGINES, uninstall_venv
            from dictare.utils.hf_download import get_hf_cache_dir

            registry = _get_model_registry()
            if cap_id not in registry:
                raise HTTPException(status_code=404, detail=f"Unknown capability: {cap_id}")

            info = registry[cap_id]
            if info.get("builtin"):
                raise HTTPException(status_code=400, detail="Cannot remove a builtin capability")

            venv_name = info.get("venv")
            repo = info.get("repo")

            if not venv_name and not repo:
                raise HTTPException(status_code=400, detail="Nothing to remove for this capability")

            if venv_name and venv_name in VENV_ENGINES:
                await asyncio.to_thread(uninstall_venv, venv_name)

            if repo:
                cache_dir = get_hf_cache_dir(repo)
                if cache_dir.exists():
                    await asyncio.to_thread(shutil.rmtree, cache_dir, True)

            return {"status": "ok"}

        @app.post("/api/capabilities/{cap_id}/select")
        async def capability_select(cap_id: str):
            """Select a capability as the active STT model or TTS engine.

            Maps capability ID to the appropriate config key/value,
            saves it, and triggers an engine restart.
            """
            from dictare.cli.models import _get_model_registry
            from dictare.config import set_config_value

            registry = _get_model_registry()
            if cap_id not in registry:
                raise HTTPException(status_code=404, detail=f"Unknown capability: {cap_id}")

            info = registry[cap_id]
            cap_type = info["type"]

            if cap_type == "stt":
                # Map registry key to stt.model value
                # "whisper-tiny" → "tiny", "parakeet-v3" → "parakeet-v3"
                if cap_id.startswith("whisper-"):
                    model_value = cap_id[len("whisper-"):]
                else:
                    model_value = cap_id
                try:
                    set_config_value("stt.model", model_value)
                    logger.info("capabilities.select stt.model=%s", model_value)
                except (KeyError, ValueError) as e:
                    raise HTTPException(status_code=422, detail=str(e))

            elif cap_type == "tts":
                # Map registry key to tts.engine value
                # "coqui-xtts-v2" → "coqui" (via venv field), "piper" → "piper"
                engine_value = info.get("venv", cap_id)
                try:
                    set_config_value("tts.engine", engine_value)
                    logger.info("capabilities.select tts.engine=%s", engine_value)
                except (KeyError, ValueError) as e:
                    raise HTTPException(status_code=422, detail=str(e))

            else:
                raise HTTPException(status_code=400, detail=f"Unknown type: {cap_type}")

            return {"status": "ok", "restart_required": True}

        return app

    def _run_model_download(
        self, model_id: str, info: dict, loop: asyncio.AbstractEventLoop
    ) -> None:
        """Download a model in a background thread, streaming SSE progress events.

        Monitors HuggingFace cache directory size at 500 ms intervals to report
        real-time progress — same approach as the terminal Rich progress bars.
        """
        import time

        from dictare.utils.hf_download import get_cache_size, get_repo_size

        repo: str = info["repo"]
        size_gb: float = info["size_gb"]

        logger.info("Downloading model %s (%.1f GB)", model_id, size_gb)

        # Get total size (API call, best-effort)
        total_bytes = int(size_gb * 1024 ** 3)
        try:
            actual = get_repo_size(repo)
            if actual:
                total_bytes = actual
        except Exception:
            pass

        def _push(event: dict) -> None:
            with self._progress_queues_lock:
                queues = list(self._progress_queues)
            for q in queues:
                loop.call_soon_threadsafe(q.put_nowait, event)

        self._download_jobs[model_id] = {
            "status": "downloading",
            "fraction": 0.0,
            "downloaded_bytes": 0,
            "total_bytes": total_bytes,
        }
        _push({"model_id": model_id, **self._download_jobs[model_id]})

        done_event = threading.Event()
        errors: list[Exception] = []

        def _do_download() -> None:
            try:
                from huggingface_hub import snapshot_download
                snapshot_download(repo)
            except Exception as exc:
                errors.append(exc)
            finally:
                done_event.set()

        threading.Thread(target=_do_download, daemon=True).start()

        while not done_event.is_set():
            done_event.wait(timeout=0.5)
            current = get_cache_size(repo)
            fraction = min(current / total_bytes, 0.99) if total_bytes > 0 else 0.0
            self._download_jobs[model_id].update({
                "fraction": fraction,
                "downloaded_bytes": current,
            })
            _push({"model_id": model_id, **self._download_jobs[model_id]})

        if errors:
            logger.error("Model %s download failed: %s", model_id, errors[0])
            job = {"status": "error", "message": str(errors[0]), "fraction": 0.0, "downloaded_bytes": 0, "total_bytes": total_bytes}
        else:
            current = get_cache_size(repo)
            logger.info("Model %s downloaded (%.1f MB)", model_id, current / 1e6)
            job = {"status": "done", "fraction": 1.0, "downloaded_bytes": current, "total_bytes": total_bytes}

        self._download_jobs[model_id] = job
        _push({"model_id": model_id, **job})

        # Clean up after 10 s so clients can read the final state
        time.sleep(_JOB_CLEANUP_DELAY)
        self._download_jobs.pop(model_id, None)

    def _run_tts_install(
        self, engine: str, loop: asyncio.AbstractEventLoop
    ) -> None:
        """Install TTS venv in a background thread, streaming progress via SSE."""
        import time

        from dictare.tts.venv import install_venv

        job_id = f"tts-install-{engine}"
        logger.info("Installing TTS venv for %s", engine)

        def _push(event: dict) -> None:
            with self._progress_queues_lock:
                queues = list(self._progress_queues)
            for q in queues:
                loop.call_soon_threadsafe(q.put_nowait, event)

        self._download_jobs[job_id] = {
            "status": "downloading",
            "fraction": 0.0,
            "message": f"Installing TTS venv for {engine}...",
        }
        _push({"model_id": job_id, **self._download_jobs[job_id]})

        def on_progress(msg: str) -> None:
            self._download_jobs[job_id].update({"message": msg, "fraction": 0.5})
            _push({"model_id": job_id, **self._download_jobs[job_id]})

        ok = install_venv(engine, on_progress=on_progress)

        if ok:
            logger.info("TTS venv for %s installed successfully", engine)
            job = {"status": "done", "fraction": 1.0, "message": f"TTS venv for {engine} installed"}
        else:
            logger.error("TTS venv install failed for %s", engine)
            job = {"status": "error", "fraction": 0.0, "message": f"Failed to install TTS venv for {engine}"}

        self._download_jobs[job_id] = job
        _push({"model_id": job_id, **job})

        time.sleep(_JOB_CLEANUP_DELAY)
        self._download_jobs.pop(job_id, None)

    def _run_capability_install(
        self, cap_id: str, info: dict, loop: asyncio.AbstractEventLoop
    ) -> None:
        """Install a capability: venv first, then model download.

        Orchestrates multi-step install, streaming progress via SSE.
        """
        import time

        from dictare.tts.venv import install_venv, is_venv_installed
        from dictare.utils.hf_download import get_cache_size, get_repo_size, is_repo_cached

        venv_name = info.get("venv")
        repo = info.get("repo")
        check_file = info.get("check_file", "config.json")
        size_gb: float = info.get("size_gb", 0)

        logger.info("Installing capability %s", cap_id)

        def _push(event: dict) -> None:
            with self._progress_queues_lock:
                queues = list(self._progress_queues)
            for q in queues:
                loop.call_soon_threadsafe(q.put_nowait, event)

        self._download_jobs[cap_id] = {
            "status": "downloading",
            "fraction": 0.0,
            "message": f"Installing {cap_id}...",
        }
        _push({"model_id": cap_id, **self._download_jobs[cap_id]})

        # Step 1: Install venv if needed
        if venv_name and not is_venv_installed(venv_name):
            self._download_jobs[cap_id].update({"message": f"Creating venv for {venv_name}...", "fraction": 0.1})
            _push({"model_id": cap_id, **self._download_jobs[cap_id]})

            def on_progress(msg: str) -> None:
                self._download_jobs[cap_id].update({"message": msg, "fraction": 0.3})
                _push({"model_id": cap_id, **self._download_jobs[cap_id]})

            ok = install_venv(venv_name, on_progress=on_progress)
            if not ok:
                logger.error("Capability %s: venv install failed", cap_id)
                job = {"status": "error", "fraction": 0.0, "message": f"Venv install failed for {venv_name}"}
                self._download_jobs[cap_id] = job
                _push({"model_id": cap_id, **job})
                time.sleep(_JOB_CLEANUP_DELAY)
                self._download_jobs.pop(cap_id, None)
                return

        # Step 2: Download model if needed
        if repo and not is_repo_cached(repo, check_file):
            total_bytes = int(size_gb * 1024 ** 3)
            try:
                actual = get_repo_size(repo)
                if actual:
                    total_bytes = actual
            except Exception:
                pass

            self._download_jobs[cap_id].update({
                "message": "Downloading model...",
                "fraction": 0.5,
                "downloaded_bytes": 0,
                "total_bytes": total_bytes,
            })
            _push({"model_id": cap_id, **self._download_jobs[cap_id]})

            import threading as _threading

            done_event = _threading.Event()
            errors: list[Exception] = []

            def _do_download() -> None:
                try:
                    from huggingface_hub import snapshot_download
                    snapshot_download(repo)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    done_event.set()

            _threading.Thread(target=_do_download, daemon=True).start()

            while not done_event.is_set():
                done_event.wait(timeout=0.5)
                current = get_cache_size(repo)
                fraction = 0.5 + 0.49 * min(current / total_bytes, 1.0) if total_bytes > 0 else 0.5
                self._download_jobs[cap_id].update({
                    "fraction": fraction,
                    "downloaded_bytes": current,
                    "message": "Downloading model...",
                })
                _push({"model_id": cap_id, **self._download_jobs[cap_id]})

            if errors:
                logger.error("Capability %s: model download failed: %s", cap_id, errors[0])
                job = {"status": "error", "fraction": 0.0, "message": str(errors[0])}
                self._download_jobs[cap_id] = job
                _push({"model_id": cap_id, **job})
                time.sleep(_JOB_CLEANUP_DELAY)
                self._download_jobs.pop(cap_id, None)
                return

        logger.info("Capability %s installed successfully", cap_id)
        job = {"status": "done", "fraction": 1.0, "message": f"{cap_id} installed"}
        self._download_jobs[cap_id] = job
        _push({"model_id": cap_id, **job})

        time.sleep(_JOB_CLEANUP_DELAY)
        self._download_jobs.pop(cap_id, None)

    def start(self) -> None:
        """Start the HTTP server in a background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="openvip-http-server",
        )
        self._thread.start()
        logger.info("OpenVIP server starting on http://%s:%s", self._host, self._port)

    def _run_server(self) -> None:
        """Run uvicorn in the background thread."""
        import uvicorn

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        config = uvicorn.Config(
            app=self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        async def _run() -> None:
            # Signal when uvicorn has bound the socket and is ready
            async def _signal_started() -> None:
                while not self._server.started:
                    await asyncio.sleep(0.01)
                self._started.set()

            task = asyncio.create_task(_signal_started())
            try:
                await self._server.serve()
            finally:
                task.cancel()

        try:
            self._loop.run_until_complete(_run())
        except OSError as e:
            import errno
            if getattr(e, "errno", None) == errno.EADDRINUSE:
                logger.error(
                    "Port %d already in use — another dictare engine is running. "
                    "Stop it first: dictare engine stop",
                    self._port,
                )
            else:
                logger.exception("OpenVIP server OS error")
            self._start_error = e
        except Exception as e:
            logger.exception("OpenVIP server error")
            self._start_error = e
        finally:
            self._started.set()  # Ensure event fires even on error
            self._loop.close()
            self._loop = None

    def stop(self) -> None:
        """Stop the HTTP server."""
        if not self._running:
            return

        self._running = False

        if self._server:
            self._server.should_exit = True

        if self._thread:
            self._thread.join(timeout=_SERVER_JOIN_TIMEOUT)
            self._thread = None

        self._server = None
        logger.info("OpenVIP server stopped")

    @property
    def port(self) -> int:
        """Actual bound port (resolves port=0 after start)."""
        if self._server and hasattr(self._server, "servers") and self._server.servers:
            sockets = self._server.servers[0].sockets
            if sockets:
                return sockets[0].getsockname()[1]
        return self._port

    def wait_started(self, timeout: float = 5.0) -> bool:
        """Block until server is ready to accept connections.

        Returns:
            True if server started successfully, False if it failed or timed out.
        """
        fired = self._started.wait(timeout)
        if not fired:
            return False
        return self._start_error is None

    def put_message(self, agent_id: str, message: dict) -> bool:
        """Thread-safe: put a message into an agent's SSE queue.

        Called from engine threads to deliver messages to SSE clients.

        Args:
            agent_id: Target agent identifier.
            message: OpenVIP message dict.

        Returns:
            True if message was queued, False if agent not connected.
        """
        with self._agent_queues_lock:
            queue = self._agent_queues.get(agent_id)

        if queue is None:
            return False

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(queue.put_nowait, message)
            return True

        return False

    def notify_status_change(self) -> None:
        """Thread-safe: push current status to all SSE status subscribers.

        Called from engine threads on state transitions and agent changes.
        """
        with self._status_queues_lock:
            if not self._status_queues:
                return
            queues = list(self._status_queues)

        if not (self._loop and self._loop.is_running()):
            return

        status = self._engine.get_status()
        for q in queues:
            self._loop.call_soon_threadsafe(q.put_nowait, status)

    @property
    def connected_agents(self) -> list[str]:
        """List of currently connected agent IDs."""
        with self._agent_queues_lock:
            return list(self._agent_queues.keys())
