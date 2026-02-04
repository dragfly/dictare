"""Engine state dataclasses.

Defines the state objects exposed via /status endpoint.
All state is in-memory and not persisted (except metrics).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

class STTState(str, Enum):
    """Speech-to-Text service states."""

    IDLE = "idle"
    LISTENING = "listening"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    ERROR = "error"

class TTSState(str, Enum):
    """Text-to-Speech service states."""

    IDLE = "idle"
    SPEAKING = "speaking"
    ERROR = "error"

class TranslationState(str, Enum):
    """Translation service states."""

    IDLE = "idle"
    TRANSLATING = "translating"
    ERROR = "error"

@dataclass
class ServiceSTTState:
    """STT service state."""

    state: STTState = STTState.IDLE
    model_loaded: bool = False
    model_name: str | None = None
    language: str = "auto"
    error: str | None = None

@dataclass
class ServiceTTSState:
    """TTS service state."""

    state: TTSState = TTSState.IDLE
    engine_loaded: bool = False
    engine_name: str | None = None
    voice: str | None = None
    error: str | None = None

@dataclass
class ServiceTranslationState:
    """Translation service state (placeholder for future)."""

    state: TranslationState = TranslationState.IDLE
    model_loaded: bool = False
    model_name: str | None = None
    source_lang: str = "auto"
    target_lang: str = "en"
    error: str | None = None

@dataclass
class ModelLoadingProgress:
    """Progress for a single model loading."""

    name: str = ""  # "stt", "vad", "tts"
    status: Literal["pending", "loading", "done", "error"] = "pending"
    started_at: float = 0.0  # time.time() when loading started
    elapsed: float = 0.0  # seconds elapsed (calculated on-the-fly)
    estimated: float = 0.0  # historical load time from stats
    error: str | None = None

@dataclass
class LoadingState:
    """Loading progress state.

    When engine is loading models, this object tracks progress.
    Progress is calculated on-the-fly: elapsed / estimated.
    """

    active: bool = True
    models: list[ModelLoadingProgress] = field(default_factory=list)

    def get_progress(self, model_name: str) -> float:
        """Get progress (0.0-1.0) for a model, calculated on-the-fly."""
        import time

        for model in self.models:
            if model.name == model_name:
                if model.status == "done":
                    return 1.0
                if model.status == "pending":
                    return 0.0
                if model.estimated <= 0:
                    return 0.0
                elapsed = time.time() - model.started_at
                # Cap at 99% until actually done
                return min(elapsed / model.estimated, 0.99)
        return 0.0

@dataclass
class OutputState:
    """Output mode state."""

    mode: Literal["keyboard", "agents"] = "keyboard"
    current_agent: str | None = None
    available_agents: list[str] = field(default_factory=list)

@dataclass
class HotkeyState:
    """Hotkey binding state.

    - bound: True if hotkey is registered and functional
    - key: The configured hotkey (e.g., "right_cmd", "f12")
    - source: "keyboard" or "device"
    - device_name: Device name if source="device"
    """

    bound: bool = False
    key: str = "right_cmd"
    source: Literal["keyboard", "device"] = "keyboard"
    device_name: str | None = None

@dataclass
class EngineMetadata:
    """Engine metadata."""

    version: str = ""
    pid: int = 0
    uptime_seconds: float = 0.0
    mode: Literal["foreground", "daemon"] = "foreground"
    started_at: str = ""  # ISO8601

@dataclass
class EngineState:
    """Complete engine state exposed via /status endpoint.

    This is the single source of truth for the engine's state.
    UI clients poll this every 500ms and render accordingly.
    """

    stt: ServiceSTTState = field(default_factory=ServiceSTTState)
    tts: ServiceTTSState = field(default_factory=ServiceTTSState)
    translation: ServiceTranslationState = field(default_factory=ServiceTranslationState)
    loading: LoadingState | None = None
    output: OutputState = field(default_factory=OutputState)
    hotkey: HotkeyState = field(default_factory=HotkeyState)
    engine: EngineMetadata = field(default_factory=EngineMetadata)

    def to_dict(self) -> dict:
        """Convert state to dictionary for JSON serialization."""
        return {
            "stt": {
                "state": self.stt.state.value,
                "model_loaded": self.stt.model_loaded,
                "model_name": self.stt.model_name,
                "language": self.stt.language,
                "error": self.stt.error,
            },
            "tts": {
                "state": self.tts.state.value,
                "engine_loaded": self.tts.engine_loaded,
                "engine_name": self.tts.engine_name,
                "voice": self.tts.voice,
                "error": self.tts.error,
            },
            "translation": {
                "state": self.translation.state.value,
                "model_loaded": self.translation.model_loaded,
                "model_name": self.translation.model_name,
                "source_lang": self.translation.source_lang,
                "target_lang": self.translation.target_lang,
                "error": self.translation.error,
            },
            "loading": (
                {
                    "active": self.loading.active,
                    "models": [
                        {
                            "name": m.name,
                            "status": m.status,
                            "progress": self.loading.get_progress(m.name),
                            "elapsed": (
                                __import__("time").time() - m.started_at
                                if m.status == "loading"
                                else m.elapsed
                            ),
                            "estimated": m.estimated,
                            "error": m.error,
                        }
                        for m in self.loading.models
                    ],
                }
                if self.loading
                else None
            ),
            "output": {
                "mode": self.output.mode,
                "current_agent": self.output.current_agent,
                "available_agents": self.output.available_agents,
            },
            "hotkey": {
                "bound": self.hotkey.bound,
                "key": self.hotkey.key,
                "source": self.hotkey.source,
                "device_name": self.hotkey.device_name,
            },
            "engine": {
                "version": self.engine.version,
                "pid": self.engine.pid,
                "uptime_seconds": self.engine.uptime_seconds,
                "mode": self.engine.mode,
                "started_at": self.engine.started_at,
            },
        }

@dataclass
class SessionMetrics:
    """Current session metrics."""

    started_at: str = ""  # ISO8601
    transcription_minutes: float = 0.0
    tts_minutes: float = 0.0
    transcriptions: int = 0
    tts_requests: int = 0

@dataclass
class LifetimeMetrics:
    """Lifetime metrics (persisted to disk)."""

    total_transcription_minutes: float = 0.0
    total_tts_minutes: float = 0.0
    total_sessions: int = 0
    total_transcriptions: int = 0
    total_tts_requests: int = 0
    first_used: str = ""  # ISO8601

@dataclass
class EngineMetrics:
    """Complete metrics exposed via /metrics endpoint."""

    lifetime: LifetimeMetrics = field(default_factory=LifetimeMetrics)
    session: SessionMetrics = field(default_factory=SessionMetrics)

    def to_dict(self) -> dict:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "lifetime": {
                "total_transcription_minutes": self.lifetime.total_transcription_minutes,
                "total_tts_minutes": self.lifetime.total_tts_minutes,
                "total_sessions": self.lifetime.total_sessions,
                "total_transcriptions": self.lifetime.total_transcriptions,
                "total_tts_requests": self.lifetime.total_tts_requests,
                "first_used": self.lifetime.first_used,
            },
            "session": {
                "started_at": self.session.started_at,
                "transcription_minutes": self.session.transcription_minutes,
                "tts_minutes": self.session.tts_minutes,
                "transcriptions": self.session.transcriptions,
                "tts_requests": self.session.tts_requests,
            },
        }
