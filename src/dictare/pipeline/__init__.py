"""Pipeline module for processing OpenVIP messages.

The pipeline applies a chain of steps to messages before sending.
Each step can:
- PASS: let the message through unchanged
- AUGMENT: modify the message (add metadata, transform text)
- CONSUME: stop the message, optionally emit different messages

The same Pipeline class is used for both filter and executor pipelines.
Steps are constructed explicitly by the engine (see
``DictareEngine._create_pipeline`` / ``_create_executor_pipeline``).
"""

from dictare.pipeline.base import (
    Executor,
    Filter,
    Pipeline,
    PipelineAction,
    PipelineResult,
    fork_message,
)
from dictare.pipeline.filters import AgentFilter, InputFilter, MuteFilter

__all__ = [
    "AgentFilter",
    "Executor",
    "Filter",
    "InputFilter",
    "MuteFilter",
    "Pipeline",
    "PipelineAction",
    "PipelineResult",
    "fork_message",
]
