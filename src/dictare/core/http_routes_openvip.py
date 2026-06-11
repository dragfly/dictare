"""OpenVIP protocol routes: agent SSE channels, speech, status, and control.

Registered on the FastAPI app by OpenVIPServer._create_app().
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from dictare.core.openvip_validator import OpenVIPValidationError, validate_message

if TYPE_CHECKING:
    from dictare.core.http_server import OpenVIPServer

logger = logging.getLogger(__name__)

# Protocol commands handled by the engine directly
PROTOCOL_COMMANDS = {"stt.start", "stt.stop", "stt.toggle", "engine.shutdown", "engine.restart", "ping", "hotkey.capture"}

# Max concurrent SSE status streams (safety net for tab leaks)
_MAX_STATUS_STREAMS: int = 5


def register_openvip_routes(app: FastAPI, server: OpenVIPServer) -> None:
    """Register OpenVIP protocol endpoints on *app*."""

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
            if not server.has_permission(request, "register_tts"):
                raise HTTPException(
                    status_code=403,
                    detail="Reserved agent ID",
                )
        # Check for duplicate connection
        with server.agent_queues_lock:
            if agent_id in server.agent_queues:
                raise HTTPException(
                    status_code=409,
                    detail=f"Agent '{agent_id}' already connected",
                )
            queue: asyncio.Queue = asyncio.Queue()
            server.agent_queues[agent_id] = queue

        # Create SSE agent and register with engine
        from dictare.agent.sse import SSEAgent

        agent = SSEAgent(agent_id, server)
        server.engine.register_agent(agent)
        is_tts = agent_id == DictareEngine.TTS_AGENT_ID
        if is_tts:
            server.tts_connected_event.set()
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
                with server.agent_queues_lock:
                    server.agent_queues.pop(agent_id, None)
                server.engine.unregister_agent(agent_id)
                if is_tts:
                    server.tts_connected_event.clear()
                logger.info("SSE agent disconnected: %s", agent_id)

        return EventSourceResponse(event_generator())

    @app.post("/openvip/agents/{agent_id}/messages")
    async def post_agent_message(agent_id: str, request: Request):
        """Send a message to a connected agent."""
        with server.agent_queues_lock:
            queue = server.agent_queues.get(agent_id)
        if queue is None:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_id}' not connected",
            )
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            return JSONResponse(
                status_code=400,
                content={"openvip": "1.0", "error": "Invalid JSON body", "code": "INVALID_FORMAT"},
            )
        try:
            validate_message(body)
        except OpenVIPValidationError as exc:
            return JSONResponse(
                status_code=400,
                content={"openvip": "1.0", "error": str(exc), "code": "INVALID_FORMAT"},
            )
        queue.put_nowait(body)
        return {"openvip": "1.0", "status": "ok"}

    @app.post("/openvip/speech")
    async def speech_request(request: Request):
        """Handle speech (TTS) request."""
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            return JSONResponse(
                status_code=400,
                content={"openvip": "1.0", "error": "Invalid JSON body", "code": "INVALID_FORMAT"},
            )
        try:
            validate_message(body)
        except OpenVIPValidationError as exc:
            return JSONResponse(
                status_code=400,
                content={"openvip": "1.0", "error": str(exc), "code": "INVALID_FORMAT"},
            )
        try:
            result = await asyncio.to_thread(
                server.engine.handle_speech, body
            )
            if result.get("status") == "error":
                return JSONResponse(
                    status_code=400,
                    content={"openvip": "1.0", "error": result["error"], "code": "INVALID_FORMAT"},
                )
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
        stopped = await asyncio.to_thread(server.engine.stop_speaking)
        return {"openvip": "1.0", "status": "ok", "stopped": stopped}

    @app.post("/api/agents/{agent_id}/focus")
    async def set_agent_focus(agent_id: str, request: Request):
        """Report terminal focus state for an agent."""
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        focused = body.get("focused")
        if not isinstance(focused, bool):
            raise HTTPException(status_code=400, detail="'focused' must be a boolean")
        server.engine.set_agent_focus(agent_id, focused)
        return {"status": "ok"}

    @app.get("/api/speech/voices")
    async def speech_voices():
        """List available voices for the current TTS engine."""
        voices = await asyncio.to_thread(server.engine.list_voices)
        return {
            "engine": server.engine.config.tts.engine,
            "voices": voices,
        }

    @app.post("/internal/tts/complete")
    async def tts_complete(request: Request):
        """Worker signals that a speak() call finished."""
        if not server.has_permission(request, "register_tts"):
            raise HTTPException(status_code=403, detail="Forbidden")
        body = await request.json()
        message_id = body.get("message_id", "")
        ok = body.get("ok", False)
        duration_ms = body.get("duration_ms", 0)
        server.engine.complete_tts(message_id, ok=ok, duration_ms=duration_ms)
        return {"status": "ok"}

    @app.get("/openvip/status")
    async def get_status():
        """Get engine status."""
        return server.engine.get_status()

    @app.get("/openvip/status/stream")
    async def sse_status_stream(request: Request):
        """SSE stream for status changes.

        Pushes a Status object on every state transition.
        Sends keepalive comments every 30s if no events.
        """
        sq: asyncio.Queue = asyncio.Queue()
        with server.status_queues_lock:
            # Evict oldest connections when at capacity
            while len(server.status_queues) >= _MAX_STATUS_STREAMS:
                evicted = server.status_queues.pop(0)
                evicted.put_nowait(None)  # sentinel → close
            server.status_queues.append(sq)

        # Send current status immediately on connect
        initial = server.engine.get_status()
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
                        if status is None:
                            break  # evicted by cap
                        yield {
                            "data": json.dumps(
                                status, ensure_ascii=False, default=str
                            ),
                        }
                    except TimeoutError:
                        yield {"comment": "keepalive"}
            finally:
                with server.status_queues_lock:
                    try:
                        server.status_queues.remove(sq)
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
                    server.engine.handle_protocol_command, body
                )
                return result

            # App commands → controller
            if server.controller is not None:
                result = await asyncio.to_thread(
                    server.controller.handle_app_command, body
                )
                return result

            return {"openvip": "1.0", "status": "error", "error": f"Unknown command: {command}"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/openvip/openapi.json")
    async def openvip_spec():
        """Serve the OpenVIP protocol spec for API discovery."""
        from starlette.responses import FileResponse
        spec = Path(__file__).parent.parent / "resources" / "openvip-openapi.json"
        if spec.exists():
            return FileResponse(str(spec), media_type="application/json")
        raise HTTPException(status_code=404, detail="OpenVIP spec not available")
