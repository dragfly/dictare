"""Webhook sender for voxtype - POST transcriptions to HTTP endpoints.

Implements OpenVIP (Open Voice Input Protocol) v1.0.
See: https://open-voice-input.org
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from voxtype import __version__

if TYPE_CHECKING:
    from voxtype.core.events import TranscriptionResult

# OpenVIP protocol version
OPENVIP_VERSION = "1.0"

# OpenVIP content type
OPENVIP_CONTENT_TYPE = "application/vnd.openvip+json"

class WebhookSender:
    """Send transcriptions to a webhook URL using OpenVIP protocol.

    Messages are sent asynchronously to avoid blocking the main thread.
    Failed requests are logged but don't interrupt the workflow.

    Message format (OpenVIP v1.0):
    {
        "openvip": "1.0",
        "type": "message",
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "text": "transcribed text",
        "timestamp": "2026-01-24T10:30:00Z",
        "language": "en",
        "audio_duration_ms": 2300,
        "transcription_ms": 150,
        "source": "voxtype/2.25.0"
    }
    """

    def __init__(
        self,
        url: str,
        timeout: float = 5.0,
    ) -> None:
        """Initialize webhook sender.

        Args:
            url: Webhook URL to POST to (OpenVIP receiver endpoint).
            timeout: Request timeout in seconds.
        """
        self.url = url
        self.timeout = timeout
        self._on_error: Any = None  # Callback for errors

    def send(
        self,
        text: str,
        language: str | None = None,
        audio_duration_ms: float | None = None,
        transcription_ms: float | None = None,
        message_type: str = "message",
    ) -> None:
        """Send a transcription to the webhook (async).

        Args:
            text: Transcribed text.
            language: Language code (e.g., "en", "it").
            audio_duration_ms: Audio duration in milliseconds.
            transcription_ms: Transcription time in milliseconds.
            message_type: OpenVIP message type (message, partial, etc.).
        """
        # Build OpenVIP message (flat structure per spec)
        message: dict[str, Any] = {
            "openvip": OPENVIP_VERSION,
            "type": message_type,
            "id": str(uuid.uuid4()),
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": f"voxtype/{__version__}",
        }

        # Optional fields
        if language:
            message["language"] = language
        if audio_duration_ms is not None:
            message["audio_duration_ms"] = int(audio_duration_ms)
        if transcription_ms is not None:
            message["transcription_ms"] = int(transcription_ms)

        # Send in background thread
        thread = threading.Thread(
            target=self._send_sync,
            args=(message,),
            daemon=True,
        )
        thread.start()

    def send_transcription(self, result: TranscriptionResult, language: str | None = None) -> None:
        """Send a TranscriptionResult to the webhook.

        Args:
            result: Transcription result from the engine.
            language: Language code.
        """
        self.send(
            text=result.text,
            language=language,
            audio_duration_ms=result.audio_duration_seconds * 1000,
            transcription_ms=result.transcription_seconds * 1000,
        )

    def send_partial(self, text: str, language: str | None = None) -> None:
        """Send a partial (interim) transcription.

        Args:
            text: Partial transcribed text.
            language: Language code.
        """
        self.send(text=text, language=language, message_type="partial")

    def send_start(self) -> None:
        """Send a start event (recording started)."""
        self._send_control("start")

    def send_end(self) -> None:
        """Send an end event (recording ended)."""
        self._send_control("end")

    def send_state(self, state: str) -> None:
        """Send a state update.

        Args:
            state: Current state (idle, listening, processing, muted).
        """
        message: dict[str, Any] = {
            "openvip": OPENVIP_VERSION,
            "type": "state",
            "id": str(uuid.uuid4()),
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": f"voxtype/{__version__}",
        }
        thread = threading.Thread(target=self._send_sync, args=(message,), daemon=True)
        thread.start()

    def _send_control(self, message_type: str) -> None:
        """Send a control message (start, end, ping)."""
        message: dict[str, Any] = {
            "openvip": OPENVIP_VERSION,
            "type": message_type,
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": f"voxtype/{__version__}",
        }
        thread = threading.Thread(target=self._send_sync, args=(message,), daemon=True)
        thread.start()

    def _send_sync(self, message: dict[str, Any]) -> None:
        """Send message synchronously (called in background thread)."""
        try:
            data = json.dumps(message, ensure_ascii=False).encode("utf-8")
            request = Request(
                self.url,
                data=data,
                headers={
                    "Content-Type": OPENVIP_CONTENT_TYPE,
                    "User-Agent": f"voxtype/{__version__}",
                },
                method="POST",
            )
            with urlopen(request, timeout=self.timeout) as response:
                # Read response to complete the request
                _ = response.read()
        except URLError as e:
            if self._on_error:
                self._on_error(f"Webhook error: {e}")
        except Exception as e:
            if self._on_error:
                self._on_error(f"Webhook error: {e}")

    def set_error_callback(self, callback: Any) -> None:
        """Set callback for error notifications.

        Args:
            callback: Function to call with error message.
        """
        self._on_error = callback
