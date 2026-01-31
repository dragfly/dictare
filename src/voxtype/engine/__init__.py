"""VoxType Engine - Central component containing all services and state.

The Engine is the heart of VoxType. It contains:
- Services (STT, TTS, Translation)
- State (exposed via /status)
- Config (exposed via /config)
- Metrics (exposed via /metrics)
- Transport layer (Unix socket + HTTP)

Usage:
    from voxtype.engine import Engine

    engine = Engine()
    engine.start()  # Foreground
    # or
    engine.start(daemon=True)  # Background
"""

from voxtype.engine.engine import Engine
from voxtype.engine.state import EngineState, ServiceState

__all__ = ["Engine", "EngineState", "ServiceState"]
