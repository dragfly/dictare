"""OpenVIP message factory.

OpenVIP (Open Voice Interaction Protocol) v1.0
See: https://open-voice-input.org

Message types:
- message: Final text to inject (OpenVIP v1.0)
- partial: Streaming partial transcription (internal, for StatusPanel)
- status: Engine state (internal, for StatusPanel)

Extension fields (x_) are added by pipeline filters, not here.
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
    language: str | None = None,
) -> dict[str, Any]:
    """Create an OpenVIP message for text injection.

    Args:
        text: Text to inject.
        submit: If True, set x_submit with enter=True.
        visual_newline: If True, set x_visual_newline flag.
        language: Language code (e.g., "en", "it"). Used by pipeline filters.

    Returns:
        OpenVIP message dict.

    Example:
        >>> msg = create_message("hello", submit=True, language="en")
        >>> msg["type"]  # "message"
        >>> msg["text"]  # "hello"
        >>> msg["x_submit"]["enter"]  # True
        >>> msg["language"]  # "en"
    """
    message = _base_message("message")
    message["text"] = text
    if submit:
        message["x_submit"] = {"enter": True}
    if visual_newline:
        message["x_visual_newline"] = True
    if language:
        message["language"] = language
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

def create_error(message: str, code: str | None = None) -> dict[str, Any]:
    """Create an OpenVIP error message.

    Convenience wrapper for create_status("error", ...).

    Args:
        message: Human-readable error message.
        code: Machine-readable error code.

    Returns:
        OpenVIP error status message dict.
    """
    return create_status("error", error_message=message, error_code=code)
