"""OpenVIP message factory - backwards compatibility re-export.

This module re-exports from voxtype.adapters.openvip.messages.
New code should import directly from voxtype.adapters.openvip.
"""

# Re-export everything from the new location for backwards compatibility
from voxtype.adapters.openvip.messages import (
    OPENVIP_VERSION,
    StatusValue,
    create_error,
    create_message,
    create_partial,
    create_status,
)

__all__ = [
    "OPENVIP_VERSION",
    "StatusValue",
    "create_error",
    "create_message",
    "create_partial",
    "create_status",
]

# Backwards compatibility alias
def create_event(event_type: str, **kwargs) -> dict:
    """Create an OpenVIP event message (deprecated, use specific factories)."""
    import uuid
    from datetime import datetime, timezone

    from voxtype import __version__

    message = {
        "openvip": OPENVIP_VERSION,
        "type": event_type,
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": f"voxtype/{__version__}",
    }
    message.update(kwargs)
    return message
