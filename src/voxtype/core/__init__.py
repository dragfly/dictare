"""Core — VoxtypeEngine, OpenVIPServer, and state machine.

This is the heart of voxtype. Key components:
- VoxtypeEngine: coordinates audio capture, STT, pipeline, and agent delivery
- OpenVIPServer (http_server.py): FastAPI+SSE server implementing OpenVIP protocol
- StateController: event-queue-based state machine (OFF → LISTENING → RECORDING → ...)
- EngineEvents: callback protocol for UI/audio feedback (used by AppController)
"""

from voxtype.core.engine import VoxtypeEngine
from voxtype.core.events import EngineEvents, InjectionResult, TranscriptionResult

__all__ = [
    "VoxtypeEngine",
    "EngineEvents",
    "TranscriptionResult",
    "InjectionResult",
]
