"""Tests for InputExecutor."""

from voxtype.pipeline import PipelineAction
from voxtype.pipeline.executors import InputExecutor

class TestInputExecutor:
    """Test InputExecutor behavior."""

    def test_name(self) -> None:
        ex = InputExecutor(write_fn=lambda t, s: None)
        assert ex.name == "input"

    def test_field(self) -> None:
        ex = InputExecutor(write_fn=lambda t, s: None)
        assert ex.field == "x_input"

    def test_no_input_passes(self) -> None:
        """Message without x_input passes through."""
        ex = InputExecutor(write_fn=lambda t, s: None)
        msg = {"text": "hello"}
        result = ex.process(msg)
        assert result.action == PipelineAction.PASS
        assert result.messages == [msg]

    def test_empty_input_passes(self) -> None:
        """Message with empty x_input passes through."""
        ex = InputExecutor(write_fn=lambda t, s: None)
        msg = {"text": "hello", "x_input": {}}
        result = ex.process(msg)
        assert result.action == PipelineAction.PASS

    def test_input_consumes_and_calls_write(self) -> None:
        """Message with x_input is consumed and write_fn is called."""
        calls = []
        ex = InputExecutor(write_fn=lambda t, s: calls.append((t, s)))
        msg = {"text": "hello", "x_input": {"submit": True, "trigger": "ok send"}}
        result = ex.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages == []
        assert calls == [("hello", True)]

    def test_input_submit_false(self) -> None:
        """x_input with submit=False still calls write_fn with False."""
        calls = []
        ex = InputExecutor(write_fn=lambda t, s: calls.append((t, s)))
        msg = {"text": "hello", "x_input": {"submit": False, "trigger": "test"}}
        # x_input is truthy (non-empty dict), so it gets processed
        result = ex.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert calls == [("hello", False)]

    def test_empty_text_with_input(self) -> None:
        """Empty text with input still calls write_fn."""
        calls = []
        ex = InputExecutor(write_fn=lambda t, s: calls.append((t, s)))
        msg = {"text": "", "x_input": {"submit": True}}
        result = ex.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert calls == [("", True)]
