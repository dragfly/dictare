"""FastAPI HTTP server for OpenVIP (Open Voice Interaction Protocol).

Provides SSE-based agent communication, TTS, status, and control endpoints.
Runs in its own background thread with a dedicated asyncio event loop.

The HTTP adapter translates HTTP requests to method calls on Engine
(protocol commands) and AppController (application commands).

Route handlers live in sibling modules, grouped by domain:
- http_routes_openvip.py  — OpenVIP protocol (agents, speech, status, control)
- http_routes_settings.py — settings, system, hotkey, permissions, audio, web UI
- http_routes_models.py   — models, capabilities, TTS venv installs
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request

from dictare import __version__
from dictare.core.http_routes_models import register_models_routes
from dictare.core.http_routes_openvip import register_openvip_routes
from dictare.core.http_routes_settings import register_settings_routes

if TYPE_CHECKING:
    from dictare.app.controller import AppController
    from dictare.core.engine import DictareEngine

logger = logging.getLogger(__name__)

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
        POST /api/audio/device            - Switch audio device instantly
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
        register_openvip_routes(app, self)
        register_settings_routes(app, self)
        register_models_routes(app, self)
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
