"""FastAPI HTTP server for OpenVIP (Open Voice Interaction Protocol).

Provides SSE-based agent communication, TTS, status, and control endpoints.
Runs in its own background thread with a dedicated asyncio event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from voxtype import __version__

if TYPE_CHECKING:
    from voxtype.core.engine import VoxtypeEngine

logger = logging.getLogger(__name__)


class OpenVIPServer:
    """FastAPI server implementing OpenVIP protocol endpoints.

    Runs in a background thread with its own asyncio event loop.
    Thread-safe message delivery via asyncio.Queue per agent.

    Endpoints:
        GET  /agents/{agent_id}/messages  - SSE stream (connection = registration)
        POST /agents/{agent_id}/messages  - Send message to agent
        POST /speech                      - Speech (TTS) request
        GET  /status                      - Engine status
        POST /control                     - Control commands
    """

    def __init__(
        self,
        engine: VoxtypeEngine,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        self._engine = engine
        self._host = host
        self._port = port

        # Agent queues: agent_id -> asyncio.Queue
        self._agent_queues: dict[str, asyncio.Queue] = {}
        self._agent_queues_lock = threading.Lock()

        # Server thread and event loop
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: Any = None  # uvicorn.Server
        self._running = False

        # FastAPI app
        self._app = self._create_app()

    def _create_app(self) -> FastAPI:
        """Create FastAPI application with all endpoints."""
        app = FastAPI(
            title="VoxType OpenVIP Server",
            version=__version__,
            docs_url=None,  # Disable docs in production
            redoc_url=None,
        )

        @app.get("/agents/{agent_id}/messages")
        async def sse_agent_messages(agent_id: str, request: Request):
            """SSE endpoint - connection IS the agent registration."""
            # Check for duplicate connection
            with self._agent_queues_lock:
                if agent_id in self._agent_queues:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Agent '{agent_id}' already connected",
                    )
                queue: asyncio.Queue = asyncio.Queue()
                self._agent_queues[agent_id] = queue

            # Register agent in engine
            self._engine._register_sse_agent(agent_id)
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
                        except asyncio.TimeoutError:
                            # Send keepalive comment
                            yield {"comment": "keepalive"}
                finally:
                    # Cleanup on disconnect
                    with self._agent_queues_lock:
                        self._agent_queues.pop(agent_id, None)
                    self._engine._unregister_sse_agent(agent_id)
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
                    self._engine._handle_tts_request, body
                )
                return result
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/status")
        async def get_status():
            """Get engine status."""
            return self._engine._get_http_status()

        @app.post("/control")
        async def control_command(request: Request):
            """Handle control commands."""
            body = await request.json()
            try:
                result = await asyncio.to_thread(
                    self._engine._handle_control, body
                )
                return result
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        return app

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

        try:
            self._loop.run_until_complete(self._server.serve())
        except Exception:
            logger.exception("OpenVIP server error")
        finally:
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

    @property
    def connected_agents(self) -> list[str]:
        """List of currently connected agent IDs."""
        with self._agent_queues_lock:
            return list(self._agent_queues.keys())
