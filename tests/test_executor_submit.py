"""Tests for SubmitExecutor."""

from voxtype.pipeline import PipelineAction
from voxtype.pipeline.executors import SubmitExecutor


class TestSubmitExecutor:
    """Test SubmitExecutor behavior."""

    def test_name(self) -> None:
        ex = SubmitExecutor(write_fn=lambda t, s: None)
        assert ex.name == "submit"

    def test_field(self) -> None:
        ex = SubmitExecutor(write_fn=lambda t, s: None)
        assert ex.field == "x_submit"

    def test_no_submit_passes(self) -> None:
        """Message without x_submit passes through."""
        ex = SubmitExecutor(write_fn=lambda t, s: None)
        msg = {"text": "hello"}
        result = ex.process(msg)
        assert result.action == PipelineAction.PASS
        assert result.messages == [msg]

    def test_empty_submit_passes(self) -> None:
        """Message with empty x_submit passes through."""
        ex = SubmitExecutor(write_fn=lambda t, s: None)
        msg = {"text": "hello", "x_submit": {}}
        result = ex.process(msg)
        assert result.action == PipelineAction.PASS

    def test_submit_consumes_and_calls_write(self) -> None:
        """Message with x_submit is consumed and write_fn is called."""
        calls = []
        ex = SubmitExecutor(write_fn=lambda t, s: calls.append((t, s)))
        msg = {"text": "hello", "x_submit": {"enter": True, "trigger": "ok send"}}
        result = ex.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages == []
        assert calls == [("hello", True)]

    def test_submit_enter_false(self) -> None:
        """x_submit with enter=False still calls write_fn with False."""
        calls = []
        ex = SubmitExecutor(write_fn=lambda t, s: calls.append((t, s)))
        msg = {"text": "hello", "x_submit": {"enter": False, "trigger": "test"}}
        # x_submit is truthy (non-empty dict), so it gets processed
        result = ex.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert calls == [("hello", False)]

    def test_empty_text_with_submit(self) -> None:
        """Empty text with submit still calls write_fn."""
        calls = []
        ex = SubmitExecutor(write_fn=lambda t, s: calls.append((t, s)))
        msg = {"text": "", "x_submit": {"enter": True}}
        result = ex.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert calls == [("", True)]
