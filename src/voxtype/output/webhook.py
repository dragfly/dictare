"""Webhook sender for voxtype - POST transcriptions to HTTP endpoints."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.request import Request, urlopen
from urllib.error import URLError

from voxtype import __version__

if TYPE_CHECKING:
    from voxtype.core.events import TranscriptionResult

class WebhookSender:
    """Send transcriptions to a webhook URL.

    Messages are sent asynchronously to avoid blocking the main thread.
    Failed requests are logged but don't interrupt the workflow.

    Message format (OpenVox-compatible):
    {
        "openvox": "1.0",
        "type": "message",
        "text": "transcribed text",
        "metadata": {
            "language": "en",
            "audio_duration_ms": 2300,
            "transcription_ms": 150,
            "timestamp": "2026-01-24T10:30:00Z"
        },
        "context": {
            "source": "voxtype",
            "source_version": "2.25.0",
            "agent": "claude"  // optional
        }
    }
    """

    def __init__(
        self,
        url: str,
        timeout: float = 5.0,
        include_metadata: bool = True,
        agent: str | None = None,
    ) -> None:
        """Initialize webhook sender.

        Args:
            url: Webhook URL to POST to.
            timeout: Request timeout in seconds.
            include_metadata: Include timing and language metadata.
            agent: Optional agent name for context.
        """
        self.url = url
        self.timeout = timeout
        self.include_metadata = include_metadata
        self.agent = agent
        self._on_error: Any = None  # Callback for errors

    def send(
        self,
        text: str,
        language: str | None = None,
        audio_duration_ms: float | None = None,
        transcription_ms: float | None = None,
    ) -> None:
        """Send a transcription to the webhook (async).

        Args:
            text: Transcribed text.
            language: Language code (e.g., "en", "it").
            audio_duration_ms: Audio duration in milliseconds.
            transcription_ms: Transcription time in milliseconds.
        """
        # Build OpenVox-compatible message
        message: dict[str, Any] = {
            "openvox": "1.0",
            "type": "message",
            "text": text,
        }

        if self.include_metadata:
            message["metadata"] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if language:
                message["metadata"]["language"] = language
            if audio_duration_ms is not None:
                message["metadata"]["audio_duration_ms"] = audio_duration_ms
            if transcription_ms is not None:
                message["metadata"]["transcription_ms"] = transcription_ms

        message["context"] = {
            "source": "voxtype",
            "source_version": __version__,
        }
        if self.agent:
            message["context"]["agent"] = self.agent

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

    def _send_sync(self, message: dict) -> None:
        """Send message synchronously (called in background thread)."""
        try:
            data = json.dumps(message, ensure_ascii=False).encode("utf-8")
            request = Request(
                self.url,
                data=data,
                headers={
                    "Content-Type": "application/json",
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
