"""Pipeline module for processing OpenVIP messages.

The pipeline applies a chain of filters to messages before sending.
Each filter can:
- PASS: let the message through unchanged
- AUGMENT: modify the message (add metadata, transform text)
- CONSUME: stop the message, optionally emit different messages

Filters are executed in the order they are configured.
"""

from voxtype.pipeline.base import (
    Filter,
    FilterAction,
    FilterResult,
    Pipeline,
)
from voxtype.pipeline.submit_filter import SubmitFilter

__all__ = [
    "Filter",
    "FilterAction",
    "FilterResult",
    "Pipeline",
    "SubmitFilter",
]
