"""Tests for AgentSwitchExecutor."""

from voxtype.pipeline import PipelineAction
from voxtype.pipeline.executors import AgentSwitchExecutor

class TestAgentSwitchExecutor:
    """Test AgentSwitchExecutor behavior."""

    def test_name(self) -> None:
        """Executor has correct name."""
        ex = AgentSwitchExecutor(switch_fn=lambda _: True)
        assert ex.name == "agent_switch"

    def test_field(self) -> None:
        """Executor declares x_agent_switch field."""
        ex = AgentSwitchExecutor(switch_fn=lambda _: True)
        assert ex.field == "x_agent_switch"

    def test_no_switch_passes(self) -> None:
        """Message without x_agent_switch passes through."""
        ex = AgentSwitchExecutor(switch_fn=lambda _: True)
        msg = {"text": "hello"}
        result = ex.process(msg)
        assert result.action == PipelineAction.PASS
        assert result.messages == [msg]

    def test_empty_switch_passes(self) -> None:
        """Message with empty x_agent_switch passes through."""
        ex = AgentSwitchExecutor(switch_fn=lambda _: True)
        msg = {"text": "hello", "x_agent_switch": {}}
        result = ex.process(msg)
        assert result.action == PipelineAction.PASS

    def test_switch_consumes_message(self) -> None:
        """Message with x_agent_switch is consumed."""
        switched_to = []
        ex = AgentSwitchExecutor(switch_fn=lambda t: (switched_to.append(t), True)[1])
        msg = {"text": "", "x_agent_switch": {"target": "voxtype", "confidence": 0.95}}
        result = ex.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages == []
        assert switched_to == ["voxtype"]

    def test_switch_calls_switch_fn(self) -> None:
        """Executor calls switch_fn with target agent name."""
        targets = []

        def mock_switch(name: str) -> bool:
            targets.append(name)
            return True

        ex = AgentSwitchExecutor(switch_fn=mock_switch)
        msg = {"text": "", "x_agent_switch": {"target": "claude"}}
        ex.process(msg)
        assert targets == ["claude"]

    def test_switch_failure_still_consumes(self) -> None:
        """Even if switch fails, message is still consumed."""
        ex = AgentSwitchExecutor(switch_fn=lambda _: False)
        msg = {"text": "", "x_agent_switch": {"target": "nonexistent"}}
        result = ex.process(msg)
        assert result.action == PipelineAction.CONSUME

    def test_no_target_passes(self) -> None:
        """x_agent_switch without target passes through."""
        ex = AgentSwitchExecutor(switch_fn=lambda _: True)
        msg = {"text": "", "x_agent_switch": {"confidence": 0.5}}
        result = ex.process(msg)
        assert result.action == PipelineAction.PASS
