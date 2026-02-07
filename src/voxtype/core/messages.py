"""OpenVIP message factory.

OpenVIP (Open Voice Interaction Protocol) v1.0
See: https://open-voice-input.org

Protocol message types:
- transcription: Transcribed text from speech-to-text (OpenVIP v1.0)
- speech: Text-to-speech request (OpenVIP v1.0)

Internal message types (NOT part of OpenVIP protocol):
- status: Engine state changes (StatusPanel)

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
        "origin": f"voxtype/{__version__}",
    }


def create_message(
    text: str,
    *,
    language: str | None = None,
    partial: bool = False,
) -> dict[str, Any]:
    """Create an OpenVIP transcription message.

    Args:
        text: Transcribed text.
        language: Language code (e.g., "en", "it").
        partial: If True, this is an incomplete transcription in progress.

    Returns:
        OpenVIP transcription message dict.

    Example:
        >>> msg = create_message("hello", language="en")
        >>> msg["type"]  # "transcription"
        >>> msg["text"]  # "hello"
    """
    message = _base_message("transcription")
    message["text"] = text
    if language:
        message["language"] = language
    if partial:
        message["partial"] = True
    return message


def create_partial(text: str) -> dict[str, Any]:
    """Create an OpenVIP partial transcription message.

    Partial messages provide streaming feedback during transcription.
    They are informational and should NOT trigger injection.

    Args:
        text: Partial transcription text.

    Returns:
        OpenVIP transcription message with partial=true.

    Example:
        >>> msg = create_partial("hel")
        >>> msg["type"]  # "transcription"
        >>> msg["partial"]  # True
    """
    return create_message(text, partial=True)


def create_status(
    status: StatusValue,
    *,
    error_message: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Create an internal status message.

    Status messages report engine state changes. These are NOT part of
    the OpenVIP protocol — they are internal to the implementation.

    Args:
        status: Current status (idle, listening, recording, transcribing, error).
        error_message: Human-readable error message (only when status="error").
        error_code: Machine-readable error code (only when status="error").

    Returns:
        Status message dict.
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
    """Create an internal error message.

    Convenience wrapper for create_status("error", ...).

    Args:
        message: Human-readable error message.
        code: Machine-readable error code.

    Returns:
        Error status message dict.
    """
    return create_status("error", error_message=message, error_code=code)
