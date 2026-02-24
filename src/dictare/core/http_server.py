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
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from dictare import __version__

if TYPE_CHECKING:
    from dictare.app.controller import AppController
    from dictare.core.engine import DictareEngine

logger = logging.getLogger(__name__)

# Protocol commands handled by the engine directly
PROTOCOL_COMMANDS = {"stt.start", "stt.stop", "stt.toggle", "engine.shutdown", "engine.restart", "ping", "hotkey.capture"}

class OpenVIPServer:
    """FastAPI server implementing OpenVIP protocol endpoints.

    Runs in a background thread with its own asyncio event loop.
    Thread-safe message delivery via asyncio.Queue per agent.

    Endpoints:
        GET  /agents/{agent_id}/messages  - SSE stream (connection = registration)
        POST /agents/{agent_id}/messages  - Send message to agent
        POST /speech                      - Speech (TTS) request
        GET  /status                      - Engine status
        GET  /status/stream               - SSE stream for status changes
        POST /control                     - Control commands
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
            title="VoxType OpenVIP Server",
            version=__version__,
            docs_url=None,  # Disable docs in production
            redoc_url=None,
        )

        @app.get("/health")
        async def health():
            """Liveness probe — returns 200 when engine is up."""
            return {"status": "ok"}

        @app.get("/agents/{agent_id}/messages")
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
            logger.info(f"SSE agent connected: {agent_id}")

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
                    logger.info(f"SSE agent disconnected: {agent_id}")

            return EventSourceResponse(event_generator())

        @app.post("/agents/{agent_id}/messages")
        async def post_agent_message(agent_id: str, request: Request):
            """Send a message to a connected agent."""
            with self._agent_queues_lock:
                queue = self._agent_queues.get(agent_id)
            if queue is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent '{agent_id}' not connected",
                )
            body = await request.json()
            queue.put_nowait(body)
            return {"status": "ok"}

        @app.post("/speech")
        async def speech_request(request: Request):
            """Handle speech (TTS) request."""
            body = await request.json()
            try:
                result = await asyncio.to_thread(
                    self._engine.handle_speech, body
                )
                return result
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/internal/tts/complete")
        async def tts_complete(request: Request):
            """Worker signals that a speak() call finished."""
            if not self._has_permission(request, "register_tts"):
                raise HTTPException(status_code=403, detail="Forbidden")
            body = await request.json()
            request_id = body.get("request_id", "")
            ok = body.get("ok", False)
            duration_ms = body.get("duration_ms", 0)
            proxy = getattr(self._engine, "_tts_proxy", None)
            if proxy is not None:
                proxy.complete(request_id, ok=ok, duration_ms=duration_ms)
            return {"status": "ok"}

        @app.get("/status")
        async def get_status():
            """Get engine status."""
            return self._engine.get_status()

        @app.get("/status/stream")
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

        @app.post("/control")
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

        @app.get("/audio/devices")
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

        @app.get("/settings/schema")
        async def settings_schema():
            """Return JSON Schema, current values, and field metadata."""
            from dictare import __version__
            from dictare.config import Config, list_config_keys, load_config

            config = load_config()
            return {
                "schema": Config.model_json_schema(),
                "values": config.model_dump(),
                "keys": [
                    {
                        "key": key,
                        "type": type_name,
                        "default": default,
                        "description": desc,
                        "env_var": env_var,
                    }
                    for key, type_name, default, desc, env_var in list_config_keys()
                ],
                "version": __version__,
            }

        @app.post("/settings")
        async def update_setting(request: Request):
            """Update a single config value."""
            from pydantic import ValidationError

            from dictare.config import (
                get_config_value,
                load_config,
                set_config_value,
            )

            body = await request.json()
            key = body.get("key", "")
            value = body.get("value")
            if not key:
                raise HTTPException(status_code=400, detail="Missing 'key'")
            try:
                set_config_value(key, str(value))
                config = load_config()
                current = get_config_value(key, config)
                logger.info("settings.change key=%s value=%r", key, current)
                return {"status": "ok", "key": key, "value": current}
            except KeyError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except (ValueError, ValidationError) as e:
                raise HTTPException(status_code=422, detail=str(e))

        @app.get("/settings/shortcuts")
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

        @app.post("/settings/shortcuts")
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

        @app.get("/settings/toml-section/{section}")
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

        @app.post("/settings/toml-section/{section}")
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

        @app.get("/models")
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
                repo = info["repo"]
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

        @app.post("/models/{model_id}/pull")
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

        @app.get("/models/pull-progress")
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
        runtime: str = info.get("runtime", "hf")
        size_gb: float = info["size_gb"]

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
                if runtime == "onnx-asr":
                    from onnx_asr import load_model as _onnx_load
                    _onnx_load(info["onnx_asr_model"])
                else:
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
            job = {"status": "error", "message": str(errors[0]), "fraction": 0.0, "downloaded_bytes": 0, "total_bytes": total_bytes}
        else:
            current = get_cache_size(repo)
            job = {"status": "done", "fraction": 1.0, "downloaded_bytes": current, "total_bytes": total_bytes}

        self._download_jobs[model_id] = job
        _push({"model_id": model_id, **job})

        # Clean up after 10 s so clients can read the final state
        time.sleep(10)
        self._download_jobs.pop(model_id, None)

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
        logger.info(f"OpenVIP server starting on http://{self._host}:{self._port}")

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
            self._thread.join(timeout=0.5)
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
