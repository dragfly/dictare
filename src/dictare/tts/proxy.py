"""TTS proxy that routes speak() to a worker subprocess via SSE queue.

WorkerTTSEngine implements the TTSEngine interface.  Instead of loading a
heavy model in-process, it sends speech requests to the ``__tts__`` worker
via the HTTP server's SSE message queue and blocks until the worker signals
completion.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from dictare.tts.base import TTSEngine

if TYPE_CHECKING:
    from dictare.core.http_server import OpenVIPServer

logger = logging.getLogger(__name__)

# Default timeout for a single speak() call (seconds)
_SPEAK_TIMEOUT = 120.0


class WorkerTTSEngine(TTSEngine):
    """Proxy TTS engine that delegates to a worker subprocess.

    The worker connects as agent ``__tts__`` via SSE.  When ``speak()`` is
    called, a speech message is placed in the agent's SSE queue.  The proxy
    then blocks on a ``threading.Event`` until the worker posts completion
    back via ``POST /internal/tts/complete``.
    """

    def __init__(self, server: OpenVIPServer) -> None:
        self._server = server
        # request_id -> (done_event, result_dict)
        self._pending: dict[str, tuple[threading.Event, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # TTSEngine interface
    # ------------------------------------------------------------------

    def speak(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> bool:
        """Send *text* to the worker and wait for completion."""
        request_id = str(uuid4())
        done = threading.Event()
        result: dict[str, Any] = {"ok": False}

        with self._lock:
            self._pending[request_id] = (done, result)

        # Deliver to the __tts__ worker via SSE.
        # Use request_id as the OpenVIP message id so the worker can echo it
        # back via /internal/tts/complete without needing extra fields.
        from dictare.core.engine import DictareEngine

        msg: dict[str, Any] = {
            "openvip": "1.0",
            "type": "speech",
            "id": request_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "text": text,
        }
        if voice:
            msg["voice"] = voice
        if language:
            msg["language"] = language

        delivered = self._server.put_message(
            DictareEngine.TTS_AGENT_ID,
            msg,
        )
        if not delivered:
            logger.warning("TTS worker not connected — speak(%r) dropped", text)
            with self._lock:
                self._pending.pop(request_id, None)
            return False

        done.wait(timeout=_SPEAK_TIMEOUT)

        with self._lock:
            self._pending.pop(request_id, None)

        if not done.is_set():
            logger.warning("TTS worker timed out for speak(%r)", text)
            return False

        return result["ok"]

    def is_available(self) -> bool:
        return self._server.is_tts_connected()

    def get_name(self) -> str:
        return "worker"

    # ------------------------------------------------------------------
    # Completion callback (called by HTTP server)
    # ------------------------------------------------------------------

    def complete(
        self, request_id: str, *, ok: bool, duration_ms: int = 0
    ) -> None:
        """Signal that the worker finished processing *request_id*."""
        with self._lock:
            entry = self._pending.get(request_id)
        if entry is None:
            logger.debug("complete(%s): no pending request (timed out?)", request_id)
            return
        done, result = entry
        result["ok"] = ok
        result["duration_ms"] = duration_ms
        done.set()
