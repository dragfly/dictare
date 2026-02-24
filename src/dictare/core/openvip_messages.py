"""OpenVIP message factory.

OpenVIP (Open Voice Interaction Protocol) v1.0
See: https://open-voice-input.org

Protocol message types:
- transcription: Transcribed text from speech-to-text (OpenVIP v1.0)
- speech: Text-to-speech request (OpenVIP v1.0)

Extension fields (x_) are added by pipeline filters, not here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from dictare import __version__

# OpenVIP protocol version
OPENVIP_VERSION = "1.0"


def _base_message(msg_type: str) -> dict[str, Any]:
    """Create base message with common fields."""
    return {
        "openvip": OPENVIP_VERSION,
        "type": msg_type,
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "origin": f"dictare/{__version__}",
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


