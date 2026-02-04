"""OpenVIP messages - re-export from core.messages.

This module is a backwards-compatibility shim. The canonical location
is now voxtype.core.messages.
"""

from voxtype.core.messages import (  # noqa: F401
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
