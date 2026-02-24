"""Pipeline executors — act on extension fields in messages."""

from dictare.pipeline.executors.agent_switch import AgentSwitchExecutor
from dictare.pipeline.executors.input import InputExecutor

__all__ = ["AgentSwitchExecutor", "InputExecutor"]
