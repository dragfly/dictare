"""Pipeline module for processing OpenVIP messages.

The pipeline applies a chain of steps to messages before sending.
Each step can:
- PASS: let the message through unchanged
- AUGMENT: modify the message (add metadata, transform text)
- CONSUME: stop the message, optionally emit different messages

The same Pipeline class is used for both filter and executor pipelines.
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
from dictare.pipeline.loader import PipelineLoader, register_step

# Register built-in steps
register_step("mute_filter", MuteFilter)
register_step("agent_filter", AgentFilter)
register_step("input_filter", InputFilter)

# Executors — imported here to register, but not re-exported
# (use dictare.pipeline.executors for direct access)
from dictare.pipeline.executors import (  # noqa: E402
    AgentSwitchExecutor,
    InputExecutor,
    MuteExecutor,
)

register_step("agent_switch", AgentSwitchExecutor)
register_step("input", InputExecutor)
register_step("mute", MuteExecutor)

__all__ = [
    "AgentFilter",
    "Executor",
    "Filter",
    "InputFilter",
    "MuteFilter",
    "Pipeline",
    "PipelineAction",
    "PipelineLoader",
    "PipelineResult",
    "fork_message",
    "register_step",
]
