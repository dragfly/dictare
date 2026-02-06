"""Pipeline module for processing OpenVIP messages.

The pipeline applies a chain of steps to messages before sending.
Each step can:
- PASS: let the message through unchanged
- AUGMENT: modify the message (add metadata, transform text)
- CONSUME: stop the message, optionally emit different messages

The same Pipeline class is used for both filter and executor pipelines.
"""

from voxtype.pipeline.agent_filter import AgentFilter
from voxtype.pipeline.base import (
    Executor,
    Filter,
    Pipeline,
    PipelineAction,
    PipelineResult,
    derive_message,
)
from voxtype.pipeline.submit_filter import SubmitFilter

__all__ = [
    "AgentFilter",
    "Executor",
    "Filter",
    "Pipeline",
    "PipelineAction",
    "PipelineResult",
    "SubmitFilter",
    "derive_message",
]
