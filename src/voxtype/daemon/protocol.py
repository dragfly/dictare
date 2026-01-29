"""Daemon protocol - JSON message types for client-server communication."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

@dataclass
class TTSRequest:
    """Request to speak text via TTS."""

    action: Literal["tts.speak"] = "tts.speak"
    text: str = ""
    engine: str | None = None
    language: str | None = None
    voice: str | None = None
    speed: int | None = None
    output: Literal["play", "wav", "mp3"] = "play"

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "text": self.text,
            "engine": self.engine,
            "language": self.language,
            "voice": self.voice,
            "speed": self.speed,
            "output": self.output,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TTSRequest:
        return cls(
            action=data.get("action", "tts.speak"),
            text=data.get("text", ""),
            engine=data.get("engine"),
            language=data.get("language"),
            voice=data.get("voice"),
            speed=data.get("speed"),
            output=data.get("output", "play"),
        )

@dataclass
class TTSResponse:
    """Response from TTS request."""

    status: Literal["ok", "error"] = "ok"
    duration_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"status": self.status}
        if self.status == "ok":
            result["duration_ms"] = self.duration_ms
        else:
            result["error"] = self.error
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TTSResponse:
        return cls(
            status=data.get("status", "ok"),
            duration_ms=data.get("duration_ms", 0),
            error=data.get("error"),
        )

@dataclass
class StatusRequest:
    """Request daemon status."""

    action: Literal["status"] = "status"

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

@dataclass
class StatusResponse:
    """Daemon status response."""

    status: Literal["ok"] = "ok"
    state: Literal["loading", "listening", "off"] = "off"
    processing_mode: Literal["transcription", "command"] = "transcription"
    progress: int = 0  # 0-100, only during loading
    loading_stage: str = ""  # "STT" | "VAD" | ""
    output_mode: str = "keyboard"  # "keyboard" | "agents"
    current_agent: str | None = None
    available_agents: list[str] | None = None
    uptime_seconds: float = 0.0
    tts_engine: str | None = None
    tts_loaded: bool = False
    stt_loaded: bool = False
    requests_served: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "state": self.state,
            "processing_mode": self.processing_mode,
            "progress": self.progress,
            "loading_stage": self.loading_stage,
            "output_mode": self.output_mode,
            "current_agent": self.current_agent,
            "available_agents": self.available_agents or [],
            "uptime_seconds": self.uptime_seconds,
            "tts_engine": self.tts_engine,
            "tts_loaded": self.tts_loaded,
            "stt_loaded": self.stt_loaded,
            "requests_served": self.requests_served,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusResponse:
        return cls(
            status=data.get("status", "ok"),
            state=data.get("state", "off"),
            processing_mode=data.get("processing_mode", "transcription"),
            progress=data.get("progress", 0),
            loading_stage=data.get("loading_stage", ""),
            output_mode=data.get("output_mode", "keyboard"),
            current_agent=data.get("current_agent"),
            available_agents=data.get("available_agents"),
            uptime_seconds=data.get("uptime_seconds", 0.0),
            tts_engine=data.get("tts_engine"),
            tts_loaded=data.get("tts_loaded", False),
            stt_loaded=data.get("stt_loaded", False),
            requests_served=data.get("requests_served", 0),
        )

@dataclass
class ShutdownRequest:
    """Request daemon shutdown."""

    action: Literal["shutdown"] = "shutdown"

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

# --- Listen control requests ---

@dataclass
class ListenStartRequest:
    """Request to start listening."""

    action: Literal["listen.start"] = "listen.start"

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

@dataclass
class ListenStopRequest:
    """Request to stop listening."""

    action: Literal["listen.stop"] = "listen.stop"

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

@dataclass
class ListenToggleRequest:
    """Request to toggle listening state."""

    action: Literal["listen.toggle"] = "listen.toggle"

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

@dataclass
class ListenResponse:
    """Response for listen control requests."""

    status: Literal["ok", "error"] = "ok"
    listening: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"status": self.status, "listening": self.listening}
        if self.error:
            result["error"] = self.error
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ListenResponse:
        return cls(
            status=data.get("status", "ok"),
            listening=data.get("listening", False),
            error=data.get("error"),
        )

@dataclass
class ModeSetRequest:
    """Request to set output mode."""

    action: Literal["mode.set"] = "mode.set"
    mode: str = "keyboard"  # "keyboard" | "agents"

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "mode": self.mode}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModeSetRequest:
        return cls(
            action=data.get("action", "mode.set"),
            mode=data.get("mode", "keyboard"),
        )

@dataclass
class ProcessingModeToggleRequest:
    """Request to toggle processing mode (transcription <-> command)."""

    action: Literal["processing_mode.toggle"] = "processing_mode.toggle"

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

@dataclass
class ProcessingModeResponse:
    """Response for processing mode toggle request."""

    status: Literal["ok", "error"] = "ok"
    processing_mode: Literal["transcription", "command"] = "transcription"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"status": self.status, "processing_mode": self.processing_mode}
        if self.error:
            result["error"] = self.error
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcessingModeResponse:
        return cls(
            status=data.get("status", "ok"),
            processing_mode=data.get("processing_mode", "transcription"),
            error=data.get("error"),
        )

@dataclass
class OkResponse:
    """Simple OK response for commands that don't return data."""

    status: Literal["ok"] = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

@dataclass
class ErrorResponse:
    """Generic error response."""

    status: Literal["error"] = "error"
    error: str = ""
    code: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error": self.error,
            "code": self.code,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

# Type alias for all request types
RequestType = (
    TTSRequest
    | StatusRequest
    | ShutdownRequest
    | ListenStartRequest
    | ListenStopRequest
    | ListenToggleRequest
    | ModeSetRequest
    | ProcessingModeToggleRequest
)

def parse_request(data: bytes) -> RequestType | None:
    """Parse incoming request from JSON bytes."""
    try:
        obj = json.loads(data.decode("utf-8"))
        action = obj.get("action", "")

        if action == "tts.speak":
            return TTSRequest.from_dict(obj)
        elif action == "status":
            return StatusRequest()
        elif action == "shutdown":
            return ShutdownRequest()
        elif action == "listen.start":
            return ListenStartRequest()
        elif action == "listen.stop":
            return ListenStopRequest()
        elif action == "listen.toggle":
            return ListenToggleRequest()
        elif action == "mode.set":
            return ModeSetRequest.from_dict(obj)
        elif action == "processing_mode.toggle":
            return ProcessingModeToggleRequest()
        else:
            return None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

# Type alias for all response types
ResponseType = (
    TTSResponse
    | StatusResponse
    | ListenResponse
    | ProcessingModeResponse
    | OkResponse
    | ErrorResponse
)

def parse_response(data: bytes) -> ResponseType | None:
    """Parse incoming response from JSON bytes."""
    try:
        obj = json.loads(data.decode("utf-8"))
        status = obj.get("status", "")

        if status == "error":
            return ErrorResponse(error=obj.get("error", ""), code=obj.get("code", "UNKNOWN"))
        elif "duration_ms" in obj:
            return TTSResponse.from_dict(obj)
        elif "uptime_seconds" in obj:
            return StatusResponse.from_dict(obj)
        elif "listening" in obj:
            return ListenResponse.from_dict(obj)
        elif "processing_mode" in obj and "uptime_seconds" not in obj:
            return ProcessingModeResponse.from_dict(obj)
        elif status == "ok" and len(obj) == 1:
            return OkResponse()
        else:
            return None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
