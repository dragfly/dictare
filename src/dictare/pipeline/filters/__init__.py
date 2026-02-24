"""Pipeline filters — enrich messages with extension fields."""

from dictare.pipeline.filters.agent_filter import AgentFilter
from dictare.pipeline.filters.input_filter import InputFilter

__all__ = ["AgentFilter", "InputFilter"]
