"""VoxType Engine - Central component containing all services and state.

The Engine is the heart of VoxType. It contains:
- Services (STT, TTS, Translation)
- State (exposed via /status)
- Config (exposed via /config)
- Metrics (exposed via /metrics)
- Transport layer (Unix socket + HTTP)

Usage:
    from voxtype.engine import Engine

    engine = Engine(config)
    engine.start()  # Foreground
    # or
    engine.start(daemon=True)  # Background

See docs/specs/engine-architecture.md for the full specification.
"""

from voxtype.engine.engine import Engine
from voxtype.engine.state import (
    EngineMetadata,
    EngineMetrics,
    EngineState,
    HotkeyState,
    LifetimeMetrics,
    LoadingState,
    OutputState,
    ServiceSTTState,
    ServiceTranslationState,
    ServiceTTSState,
    SessionMetrics,
    STTState,
    TranslationState,
    TTSState,
)

__all__ = [
    # Main class
    "Engine",
    # State classes
    "EngineState",
    "ServiceSTTState",
    "ServiceTTSState",
    "ServiceTranslationState",
    "LoadingState",
    "OutputState",
    "HotkeyState",
    "EngineMetadata",
    # State enums
    "STTState",
    "TTSState",
    "TranslationState",
    # Metrics
    "EngineMetrics",
    "SessionMetrics",
    "LifetimeMetrics",
]
