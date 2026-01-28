"""Daemon protocol - JSON message types for client-server communication."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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
    uptime_seconds: float = 0.0
    tts_engine: str | None = None
    tts_loaded: bool = False
    stt_loaded: bool = False
    requests_served: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
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

def parse_request(data: bytes) -> TTSRequest | StatusRequest | ShutdownRequest | None:
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
        else:
            return None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

def parse_response(data: bytes) -> TTSResponse | StatusResponse | ErrorResponse | None:
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
        else:
            return None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
