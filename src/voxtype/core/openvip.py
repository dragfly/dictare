"""OpenVIP message factory - single point of message creation.

OpenVIP (Open Voice Input Protocol) v1.0
See: https://open-voice-input.org

v1.0 Message Types:
- message: Final text to inject
- partial: Streaming partial transcription
- status: Engine state (idle, listening, recording, transcribing, error)

This module provides the canonical way to create OpenVIP messages.
All transports should use these functions instead of creating messages directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from voxtype import __version__

# OpenVIP protocol version
OPENVIP_VERSION = "1.0"

# Valid status values
StatusValue = Literal["idle", "listening", "recording", "transcribing", "loading", "error"]

def _base_message(msg_type: str) -> dict[str, Any]:
    """Create base message with common fields."""
    return {
        "openvip": OPENVIP_VERSION,
        "type": msg_type,
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": f"voxtype/{__version__}",
    }

def create_message(
    text: str,
    *,
    submit: bool = False,
    visual_newline: bool = False,
) -> dict[str, Any]:
    """Create an OpenVIP message for text injection.

    Args:
        text: Text to inject.
        submit: If True, send Enter after text (x_submit flag).
        visual_newline: If True, send visual newline after text (x_visual_newline flag).

    Returns:
        OpenVIP message dict.

    Example:
        >>> msg = create_message("hello", submit=True)
        >>> msg["type"]  # "message"
        >>> msg["text"]  # "hello"
        >>> msg["x_submit"]  # True
    """
    message = _base_message("message")
    message["text"] = text
    if submit:
        message["x_submit"] = True
    if visual_newline:
        message["x_visual_newline"] = True
    return message

def create_partial(text: str) -> dict[str, Any]:
    """Create an OpenVIP partial transcription message.

    Partial messages provide streaming feedback during transcription.
    They are informational and should NOT trigger injection.

    Args:
        text: Partial transcription text.

    Returns:
        OpenVIP partial message dict.

    Example:
        >>> msg = create_partial("hel")
        >>> msg["type"]  # "partial"
        >>> msg["text"]  # "hel"
    """
    message = _base_message("partial")
    message["text"] = text
    return message

def create_status(
    status: StatusValue,
    *,
    error_message: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Create an OpenVIP status message.

    Status messages report engine state changes.

    Args:
        status: Current status (idle, listening, recording, transcribing, error).
        error_message: Human-readable error message (only when status="error").
        error_code: Machine-readable error code (only when status="error").

    Returns:
        OpenVIP status message dict.

    Example:
        >>> msg = create_status("listening")
        >>> msg["type"]  # "status"
        >>> msg["status"]  # "listening"

        >>> msg = create_status("error", error_message="Mic not found", error_code="MIC_NOT_FOUND")
        >>> msg["status"]  # "error"
        >>> msg["error"]["message"]  # "Mic not found"
    """
    message = _base_message("status")
    message["status"] = status
    if status == "error" and (error_message or error_code):
        message["error"] = {}
        if error_message:
            message["error"]["message"] = error_message
        if error_code:
            message["error"]["code"] = error_code
    return message

# Backwards compatibility alias
def create_event(event_type: str, **kwargs: Any) -> dict[str, Any]:
    """Create an OpenVIP event message (deprecated, use specific factories)."""
    message = _base_message(event_type)
    message.update(kwargs)
    return message
