"""OpenVIP adapter - exposes VoxtypeEngine via OpenVIP protocol.

OpenVIP (Open Voice Input Protocol) v1.0
See: https://open-voice-input.org

This package contains:
- adapter.py: OpenVIPAdapter class (HTTP + Unix socket server)
- messages.py: OpenVIP message creation functions
"""

from voxtype.adapters.openvip.adapter import OpenVIPAdapter
from voxtype.adapters.openvip.messages import (
    OPENVIP_VERSION,
    create_message,
    create_partial,
    create_status,
)

__all__ = [
    "OpenVIPAdapter",
    "OPENVIP_VERSION",
    "create_message",
    "create_partial",
    "create_status",
]
