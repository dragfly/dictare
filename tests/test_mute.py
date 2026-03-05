"""Tests for voice mute filter and executor."""

from dictare.pipeline import Pipeline, PipelineAction
from dictare.pipeline.executors.mute import MuteExecutor
from dictare.pipeline.filters.mute_filter import MuteFilter

# Default triggers matching config defaults
_MUTE_TRIGGERS: dict[str, list[list[str]]] = {"*": [["ok|okay", "mute|stop"]]}
_LISTEN_TRIGGERS: dict[str, list[list[str]]] = {"*": [["ok|okay", "listen"]]}

def _make_filter(*, muted: bool = False, **kwargs) -> MuteFilter:
    """Create MuteFilter with test defaults."""
    kwargs.setdefault("mute_triggers", _MUTE_TRIGGERS)
    kwargs.setdefault("listen_triggers", _LISTEN_TRIGGERS)
    kwargs.setdefault("is_muted", lambda: muted)
    return MuteFilter(**kwargs)

class TestMuteFilterBasics:
    """Test MuteFilter basic operations."""

    def test_name_property(self) -> None:
        f = MuteFilter()
        assert f.name == "mute_filter"

    def test_empty_text_passes_when_not_muted(self) -> None:
        f = _make_filter(muted=False)
        msg = {"text": ""}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS

    def test_empty_text_consumed_when_muted(self) -> None:
        f = _make_filter(muted=True)
        msg = {"text": ""}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages == []

    def test_normal_text_passes_when_not_muted(self) -> None:
        f = _make_filter(muted=False)
        msg = {"text": "fix the bug in the parser"}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS
        assert result.messages[0]["text"] == "fix the bug in the parser"

class TestMuteFilterMuteTrigger:
    """Test mute trigger detection."""

    def test_ok_mute_triggers_mute(self) -> None:
        f = _make_filter(muted=False)
        msg = {"text": "ok mute"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert len(result.messages) == 1
        assert result.messages[0]["x_mute"]["action"] == "mute"

    def test_okay_stop_triggers_mute(self) -> None:
        f = _make_filter(muted=False)
        msg = {"text": "okay stop"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages[0]["x_mute"]["action"] == "mute"

    def test_mute_trigger_with_preceding_text(self) -> None:
        f = _make_filter(muted=False)
        msg = {"text": "some random words ok mute"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages[0]["x_mute"]["action"] == "mute"
        # Preceding text is discarded (the whole message is a mute command)
        assert result.messages[0]["text"] == ""

    def test_case_insensitive_mute(self) -> None:
        f = _make_filter(muted=False)
        msg = {"text": "OK MUTE"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages[0]["x_mute"]["action"] == "mute"

    def test_mute_trigger_has_confidence(self) -> None:
        f = _make_filter(muted=False)
        msg = {"text": "ok mute"}
        result = f.process(msg)
        assert result.messages[0]["x_mute"]["confidence"] > 0.85

class TestMuteFilterListenTrigger:
    """Test listen trigger detection."""

    def test_ok_listen_unmutes(self) -> None:
        f = _make_filter(muted=True)
        msg = {"text": "ok listen"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert len(result.messages) == 1
        assert result.messages[0]["x_mute"]["action"] == "unmute"

    def test_okay_listen_unmutes(self) -> None:
        f = _make_filter(muted=True)
        msg = {"text": "okay listen"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages[0]["x_mute"]["action"] == "unmute"

    def test_listen_trigger_only_works_when_muted(self) -> None:
        """Listen trigger is not detected when not muted (it's just normal text)."""
        f = _make_filter(muted=False)
        msg = {"text": "ok listen"}
        result = f.process(msg)
        # "ok listen" is NOT a mute trigger, so it passes through
        assert result.action == PipelineAction.PASS

class TestMuteFilterDiscard:
    """Test that muted state discards text."""

    def test_discards_text_when_muted(self) -> None:
        f = _make_filter(muted=True)
        msg = {"text": "fix the bug in the parser"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages == []

    def test_discards_any_text_when_muted(self) -> None:
        f = _make_filter(muted=True)
        for text in ["hello world", "ok send", "agent dictare", "submit"]:
            result = f.process({"text": text})
            assert result.action == PipelineAction.CONSUME
            # Only "ok listen" should produce output

class TestMuteFilterLanguage:
    """Test language-based trigger patterns."""

    def test_language_specific_mute_trigger(self) -> None:
        f = MuteFilter(
            mute_triggers={"de": [["ok", "stumm"]]},
            listen_triggers={"de": [["ok", "hoer"]]},
            is_muted=lambda: False,
        )
        msg = {"text": "ok stumm", "language": "de"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages[0]["x_mute"]["action"] == "mute"

    def test_wildcard_works_with_any_language(self) -> None:
        f = _make_filter(muted=False)
        msg = {"text": "ok mute", "language": "de"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages[0]["x_mute"]["action"] == "mute"

class TestMuteExecutor:
    """Test MuteExecutor."""

    def test_name_and_field(self) -> None:
        e = MuteExecutor(mute_fn=lambda: None, unmute_fn=lambda: None)
        assert e.name == "mute"
        assert e.field == "x_mute"

    def test_calls_mute_fn(self) -> None:
        calls: list[str] = []
        e = MuteExecutor(
            mute_fn=lambda: calls.append("mute"),
            unmute_fn=lambda: calls.append("unmute"),
        )
        msg = {"text": "", "x_mute": {"action": "mute", "trigger": "ok mute"}}
        result = e.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert calls == ["mute"]

    def test_calls_unmute_fn(self) -> None:
        calls: list[str] = []
        e = MuteExecutor(
            mute_fn=lambda: calls.append("mute"),
            unmute_fn=lambda: calls.append("unmute"),
        )
        msg = {"text": "", "x_mute": {"action": "unmute", "trigger": "ok listen"}}
        result = e.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert calls == ["unmute"]

    def test_passes_without_x_mute(self) -> None:
        e = MuteExecutor(mute_fn=lambda: None, unmute_fn=lambda: None)
        msg = {"text": "hello world"}
        result = e.process(msg)
        assert result.action == PipelineAction.PASS
        assert result.messages[0]["text"] == "hello world"

    def test_unknown_action_passes(self) -> None:
        e = MuteExecutor(mute_fn=lambda: None, unmute_fn=lambda: None)
        msg = {"text": "", "x_mute": {"action": "toggle"}}
        result = e.process(msg)
        assert result.action == PipelineAction.PASS

class TestMuteFilterInPipeline:
    """Test MuteFilter integration with Pipeline."""

    def test_mute_filter_first_in_pipeline(self) -> None:
        """Mute filter runs before other filters."""
        from dictare.pipeline.filters.input_filter import InputFilter

        muted_state = [False]
        mute_f = MuteFilter(
            mute_triggers=_MUTE_TRIGGERS,
            listen_triggers=_LISTEN_TRIGGERS,
            is_muted=lambda: muted_state[0],
        )
        input_f = InputFilter(triggers={"*": [["ok", "send"]]})

        p = Pipeline([mute_f, input_f])

        # Normal text passes through both filters
        result = p.process({"text": "hello world"})
        assert len(result) == 1
        assert result[0]["text"] == "hello world"

        # Mute command is consumed (doesn't reach input filter)
        result = p.process({"text": "ok mute"})
        assert len(result) == 1
        assert "x_mute" in result[0]

    def test_muted_discards_before_input_filter(self) -> None:
        """When muted, text is discarded before reaching input filter."""
        from dictare.pipeline.filters.input_filter import InputFilter

        mute_f = MuteFilter(
            mute_triggers=_MUTE_TRIGGERS,
            listen_triggers=_LISTEN_TRIGGERS,
            is_muted=lambda: True,  # Always muted
        )
        input_f = InputFilter(triggers={"*": [["ok", "send"]]})

        p = Pipeline([mute_f, input_f])

        # Even "ok send" is discarded when muted (doesn't reach input filter)
        result = p.process({"text": "fix bug ok send"})
        assert result == []

    def test_mute_executor_in_pipeline(self) -> None:
        """MuteExecutor processes x_mute messages from filter."""
        calls: list[str] = []
        e = MuteExecutor(
            mute_fn=lambda: calls.append("mute"),
            unmute_fn=lambda: calls.append("unmute"),
        )
        p = Pipeline([e])

        # Process mute message
        msg = {"text": "", "x_mute": {"action": "mute", "trigger": "ok mute"}}
        result = p.process(msg)
        assert result == []  # Consumed
        assert calls == ["mute"]

        # Regular message passes through
        msg2 = {"text": "hello"}
        result2 = p.process(msg2)
        assert len(result2) == 1
        assert result2[0]["text"] == "hello"
