"""Pipeline executors — act on extension fields in messages."""

from dictare.pipeline.executors.agent_switch import AgentSwitchExecutor
from dictare.pipeline.executors.input import InputExecutor
from dictare.pipeline.executors.mute import MuteExecutor

__all__ = ["AgentSwitchExecutor", "InputExecutor", "MuteExecutor"]
