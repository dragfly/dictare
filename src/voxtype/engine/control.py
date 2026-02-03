"""OpenVIP control command handlers.

Handles incoming control commands and dispatches to appropriate services.
All commands are idempotent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from voxtype.engine.engine import Engine

logger = logging.getLogger(__name__)


@dataclass
class ControlResponse:
    """Response to a control command."""

    status: str  # "ok" or "error"
    error_code: str | None = None
    error_message: str | None = None


class ControlHandler:
    """Handles OpenVIP control commands.

    All commands are idempotent:
    - stt.start when already listening → no-op, returns ok
    - stt.stop when already idle → no-op, returns ok
    - hotkey.bind when already bound → no-op, returns ok
    """

    def __init__(self, engine: Engine) -> None:
        """Initialize control handler.

        Args:
            engine: The engine instance to control.
        """
        self._engine = engine

        # Command dispatch table
        self._handlers: dict[str, Any] = {
            "stt.start": self._handle_stt_start,
            "stt.stop": self._handle_stt_stop,
            "tts.speak": self._handle_tts_speak,
            "tts.stop": self._handle_tts_stop,
            "output.set_mode": self._handle_output_set_mode,
            "output.set_agent": self._handle_output_set_agent,
            "hotkey.bind": self._handle_hotkey_bind,
            "hotkey.unbind": self._handle_hotkey_unbind,
            "engine.shutdown": self._handle_engine_shutdown,
            "ping": self._handle_ping,
        }

    def handle_command(self, message: dict) -> dict:
        """Handle an OpenVIP control command.

        Args:
            message: OpenVIP control message with command and payload.

        Returns:
            OpenVIP control response message.
        """
        # Extract command and ID
        command = message.get("command", "")
        msg_id = message.get("id", str(uuid4()))
        payload = message.get("payload", {})

        # Find handler
        handler = self._handlers.get(command)
        if not handler:
            return self._create_response(
                msg_id,
                ControlResponse(
                    status="error",
                    error_code="INVALID_COMMAND",
                    error_message=f"Unknown command: {command}",
                ),
            )

        # Execute handler
        try:
            result = handler(payload)
            return self._create_response(msg_id, result)
        except Exception as e:
            logger.exception(f"Error handling command {command}")
            return self._create_response(
                msg_id,
                ControlResponse(
                    status="error",
                    error_code="INTERNAL_ERROR",
                    error_message=str(e),
                ),
            )

    def _create_response(self, msg_id: str, result: ControlResponse) -> dict[str, Any]:
        """Create OpenVIP control response message."""
        response: dict[str, Any] = {
            "openvip": "1.0",
            "type": "control.response",
            "id": msg_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": result.status,
        }

        if result.error_code:
            response["error"] = {
                "code": result.error_code,
                "message": result.error_message,
            }

        return response

    # -------------------------------------------------------------------------
    # STT Commands
    # -------------------------------------------------------------------------

    def _handle_stt_start(self, payload: dict) -> ControlResponse:
        """Handle stt.start command.

        Payload:
            continuous: bool (default True) - continuous vs one-shot mode
        """
        continuous = payload.get("continuous", True)

        # Idempotent: if already listening, no-op
        if self._engine.stt_service and self._engine.stt_service.is_listening:
            return ControlResponse(status="ok")

        # Start STT
        try:
            self._engine.start_stt(continuous=continuous)
            return ControlResponse(status="ok")
        except Exception as e:
            return ControlResponse(
                status="error",
                error_code="STT_START_FAILED",
                error_message=str(e),
            )

    def _handle_stt_stop(self, payload: dict) -> ControlResponse:
        """Handle stt.stop command."""
        # Idempotent: if already idle, no-op
        if not self._engine.stt_service or not self._engine.stt_service.is_listening:
            return ControlResponse(status="ok")

        try:
            self._engine.stop_stt()
            return ControlResponse(status="ok")
        except Exception as e:
            return ControlResponse(
                status="error",
                error_code="STT_STOP_FAILED",
                error_message=str(e),
            )

    # -------------------------------------------------------------------------
    # TTS Commands
    # -------------------------------------------------------------------------

    def _handle_tts_speak(self, payload: dict) -> ControlResponse:
        """Handle tts.speak command.

        Payload:
            text: str (required) - text to speak
            voice: str (optional) - voice to use
            speed: float (optional) - speech speed
        """
        text = payload.get("text", "")
        if not text:
            return ControlResponse(
                status="error",
                error_code="INVALID_PAYLOAD",
                error_message="text is required",
            )

        voice = payload.get("voice")
        speed = payload.get("speed")

        try:
            self._engine.speak(text, voice=voice, speed=speed)
            return ControlResponse(status="ok")
        except Exception as e:
            return ControlResponse(
                status="error",
                error_code="TTS_SPEAK_FAILED",
                error_message=str(e),
            )

    def _handle_tts_stop(self, payload: dict) -> ControlResponse:
        """Handle tts.stop command."""
        try:
            self._engine.stop_tts()
            return ControlResponse(status="ok")
        except Exception as e:
            return ControlResponse(
                status="error",
                error_code="TTS_STOP_FAILED",
                error_message=str(e),
            )

    # -------------------------------------------------------------------------
    # Output Commands
    # -------------------------------------------------------------------------

    def _handle_output_set_mode(self, payload: dict) -> ControlResponse:
        """Handle output.set_mode command.

        Payload:
            mode: "keyboard" | "agents"
        """
        mode = payload.get("mode")
        if mode not in ("keyboard", "agents"):
            return ControlResponse(
                status="error",
                error_code="INVALID_PAYLOAD",
                error_message='mode must be "keyboard" or "agents"',
            )

        self._engine.state.output.mode = mode
        return ControlResponse(status="ok")

    def _handle_output_set_agent(self, payload: dict) -> ControlResponse:
        """Handle output.set_agent command.

        Payload:
            agent: str - agent name/id
        """
        agent = payload.get("agent")
        if not agent:
            return ControlResponse(
                status="error",
                error_code="INVALID_PAYLOAD",
                error_message="agent is required",
            )

        if agent not in self._engine.state.output.available_agents:
            return ControlResponse(
                status="error",
                error_code="AGENT_NOT_FOUND",
                error_message=f"Agent not found: {agent}",
            )

        self._engine.state.output.current_agent = agent
        return ControlResponse(status="ok")

    # -------------------------------------------------------------------------
    # Hotkey Commands
    # -------------------------------------------------------------------------

    def _handle_hotkey_bind(self, payload: dict) -> ControlResponse:
        """Handle hotkey.bind command.

        Notifies the engine that a client has registered the hotkey.
        The engine updates state.hotkey.bound = true.
        """
        # Idempotent: if already bound, no-op
        if self._engine.state.hotkey.bound:
            return ControlResponse(status="ok")

        self._engine.state.hotkey.bound = True
        return ControlResponse(status="ok")

    def _handle_hotkey_unbind(self, payload: dict) -> ControlResponse:
        """Handle hotkey.unbind command.

        Notifies the engine that a client has released the hotkey.
        The engine updates state.hotkey.bound = false.
        """
        # Idempotent: if already unbound, no-op
        if not self._engine.state.hotkey.bound:
            return ControlResponse(status="ok")

        self._engine.state.hotkey.bound = False
        return ControlResponse(status="ok")

    # -------------------------------------------------------------------------
    # Engine Commands
    # -------------------------------------------------------------------------

    def _handle_engine_shutdown(self, payload: dict) -> ControlResponse:
        """Handle engine.shutdown command.

        Initiates graceful shutdown of the engine.
        """
        self._engine.request_shutdown()
        return ControlResponse(status="ok")

    def _handle_ping(self, payload: dict) -> ControlResponse:
        """Handle ping command.

        Health check that responds with pong.
        """
        return ControlResponse(status="ok")
