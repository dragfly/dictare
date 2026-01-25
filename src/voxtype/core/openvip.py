"""OpenVIP message factory - single point of message creation.

OpenVIP (Open Voice Input Protocol) v1.0
See: https://open-voice-input.org

This module provides the canonical way to create OpenVIP messages.
All transports should use these functions instead of creating messages directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from voxtype import __version__

# OpenVIP protocol version
OPENVIP_VERSION = "1.0"

def create_message(
    text: str,
    *,
    submit: bool = False,
    visual_newline: bool = False,
) -> dict[str, Any]:
    """Create an OpenVIP message for text injection.

    This is the ONLY place where injection messages should be created.
    All transports receive this message and forward it transparently.

    Args:
        text: Text to inject.
        submit: If True, send Enter after text (x_submit flag).
        visual_newline: If True, send visual newline after text (x_visual_newline flag).

    Returns:
        OpenVIP message dict with id, timestamp, source, and text.

    Example:
        >>> msg = create_message("hello", submit=True)
        >>> msg["id"]  # UUID string
        >>> msg["text"]  # "hello"
        >>> msg["x_submit"]  # True
    """
    message: dict[str, Any] = {
        "openvip": OPENVIP_VERSION,
        "type": "message",
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": f"voxtype/{__version__}",
        "text": text,
    }
    if submit:
        message["x_submit"] = True
    if visual_newline:
        message["x_visual_newline"] = True
    return message

def create_event(
    event_type: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create an OpenVIP event message (state, partial, error, etc.).

    Args:
        event_type: Event type (state, partial, start, end, error).
        **kwargs: Additional fields for the event.

    Returns:
        OpenVIP event dict.
    """
    message: dict[str, Any] = {
        "openvip": OPENVIP_VERSION,
        "type": event_type,
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": f"voxtype/{__version__}",
    }
    message.update(kwargs)
    return message
