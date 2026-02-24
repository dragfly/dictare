"""Core — DictareEngine, OpenVIPServer, and state machine.

This is the heart of dictare. Key components:
- DictareEngine: coordinates audio capture, STT, pipeline, and agent delivery
- OpenVIPServer (http_server.py): FastAPI+SSE server implementing OpenVIP protocol
- StateController: event-queue-based state machine (OFF → LISTENING → RECORDING → ...)
- EngineEvents: callback protocol for UI/audio feedback (used by AppController)

Note: DictareEngine is NOT re-exported here to avoid circular imports
(core.engine imports pipeline, which imports core.bus via core/__init__).
Import directly: ``from dictare.core.engine import DictareEngine``
"""

from dictare.core.bus import EventBus, bus
from dictare.core.events import EngineEvents

__all__ = [
    "EventBus",
    "EngineEvents",
    "bus",
]
