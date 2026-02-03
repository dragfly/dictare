"""Tests for the pipeline filter system."""


from voxtype.pipeline import (
    FilterAction,
    FilterResult,
    Pipeline,
    SubmitFilter,
)
from voxtype.pipeline.submit_filter import (
    DEFAULT_SUBMIT_TRIGGERS,
    _normalize,
    _tokenize,
)


class TestHelperFunctions:
    """Test helper functions for text processing."""

    def test_normalize_lowercase(self) -> None:
        """Normalize converts to lowercase."""
        assert _normalize("HELLO") == "hello"
        assert _normalize("Hello World") == "hello world"

    def test_normalize_removes_accents(self) -> None:
        """Normalize removes accents."""
        assert _normalize("café") == "cafe"
        assert _normalize("naïve") == "naive"
        assert _normalize("résumé") == "resume"

    def test_tokenize_splits_on_non_alphanumeric(self) -> None:
        """Tokenize splits on non-alphanumeric characters."""
        assert _tokenize("hello world") == ["hello", "world"]
        assert _tokenize("hello, world!") == ["hello", "world"]
        assert _tokenize("ok invia") == ["ok", "invia"]

    def test_tokenize_filters_empty(self) -> None:
        """Tokenize filters empty tokens."""
        assert _tokenize("  hello   world  ") == ["hello", "world"]
        assert _tokenize("...test...") == ["test"]


class TestFilterResult:
    """Test FilterResult factory methods."""

    def test_passed_creates_pass_action(self) -> None:
        """FilterResult.passed creates PASS action with message."""
        msg = {"text": "hello"}
        result = FilterResult.passed(msg)
        assert result.action == FilterAction.PASS
        assert result.messages == [msg]

    def test_augmented_creates_augment_action(self) -> None:
        """FilterResult.augmented creates AUGMENT action with message."""
        msg = {"text": "hello", "x_submit": True}
        result = FilterResult.augmented(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages == [msg]

    def test_consumed_creates_consume_action(self) -> None:
        """FilterResult.consumed creates CONSUME action."""
        result = FilterResult.consumed()
        assert result.action == FilterAction.CONSUME
        assert result.messages == []

    def test_consumed_with_messages(self) -> None:
        """FilterResult.consumed can include output messages."""
        msgs = [{"text": "a"}, {"text": "b"}]
        result = FilterResult.consumed(msgs)
        assert result.action == FilterAction.CONSUME
        assert result.messages == msgs


class TestSubmitFilterBasics:
    """Test SubmitFilter basic operations."""

    def test_default_triggers(self) -> None:
        """SubmitFilter has default triggers."""
        f = SubmitFilter()
        assert f.triggers == DEFAULT_SUBMIT_TRIGGERS
        assert ["ok", "invia"] in f.triggers
        assert ["submit"] in f.triggers

    def test_custom_triggers(self) -> None:
        """SubmitFilter accepts custom triggers."""
        custom = [["done"], ["finish"]]
        f = SubmitFilter(triggers=custom)
        assert f.triggers == custom

    def test_name_property(self) -> None:
        """SubmitFilter has correct name."""
        f = SubmitFilter()
        assert f.name == "submit_filter"

    def test_empty_text_passes(self) -> None:
        """Empty text passes through unchanged."""
        f = SubmitFilter()
        msg = {"text": ""}
        result = f.process(msg)
        assert result.action == FilterAction.PASS
        assert result.messages[0]["text"] == ""

    def test_existing_submit_flag_passes(self) -> None:
        """Message with existing x_submit passes through."""
        f = SubmitFilter()
        msg = {"text": "hello submit", "x_submit": True}
        result = f.process(msg)
        assert result.action == FilterAction.PASS
        assert result.messages[0] == msg


class TestSubmitFilterTriggerDetection:
    """Test SubmitFilter trigger detection."""

    def test_single_word_trigger_at_end(self) -> None:
        """Single word trigger at end is detected."""
        f = SubmitFilter()
        msg = {"text": "hello world submit"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_submit"] is True
        assert result.messages[0]["text"] == "hello world"

    def test_italian_invia_trigger(self) -> None:
        """Italian 'invia' trigger is detected."""
        f = SubmitFilter()
        msg = {"text": "ho un bug nel parser invia"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_submit"] is True
        assert result.messages[0]["text"] == "ho un bug nel parser"

    def test_multi_word_trigger(self) -> None:
        """Multi-word trigger (ok invia) is detected."""
        f = SubmitFilter()
        msg = {"text": "fammi vedere il codice ok invia"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_submit"] is True
        assert "ok" not in result.messages[0]["text"]
        assert "invia" not in result.messages[0]["text"]

    def test_trigger_in_middle_not_detected(self) -> None:
        """Trigger in middle of text (far from end) is not detected."""
        f = SubmitFilter()
        # Many words after the trigger, beyond max_scan_words
        words = ["submit"] + ["word"] * 20 + ["end"]
        msg = {"text": " ".join(words)}
        result = f.process(msg)
        # Should pass through because submit is too far from end
        assert result.action == FilterAction.PASS

    def test_case_insensitive(self) -> None:
        """Trigger detection is case insensitive."""
        f = SubmitFilter()
        msg = {"text": "hello SUBMIT"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_submit"] is True

    def test_accent_insensitive(self) -> None:
        """Trigger detection ignores accents."""
        f = SubmitFilter(triggers=[["invìa"]])  # With accent
        msg = {"text": "test invia"}  # Without accent
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT

    def test_visual_newline_removed_on_submit(self) -> None:
        """x_visual_newline is removed when x_submit is set."""
        f = SubmitFilter()
        msg = {"text": "hello submit", "x_visual_newline": True}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_submit"] is True
        assert "x_visual_newline" not in result.messages[0]


class TestSubmitFilterConfidence:
    """Test SubmitFilter confidence-based detection."""

    def test_high_confidence_at_end(self) -> None:
        """Trigger at very end has high confidence."""
        f = SubmitFilter(confidence_threshold=0.85)
        msg = {"text": "test invia"}  # invia is last word
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT

    def test_low_confidence_far_from_end(self) -> None:
        """Trigger far from end has low confidence."""
        f = SubmitFilter(confidence_threshold=0.85, max_scan_words=15)
        # invia is 7 words from end
        # Single word patterns get 1.1x boost for "consecutive"
        # So we need: 0.95^n * 1.1 < 0.85, meaning n >= 4 → 0.95^4 * 1.1 = 0.895
        # Need n >= 5 → 0.95^5 * 1.1 = 0.851 (still >= 0.85)
        # Need n >= 6 → 0.95^6 * 1.1 = 0.808 < 0.85
        msg = {"text": "invia one two three four five six seven"}
        result = f.process(msg)
        assert result.action == FilterAction.PASS

    def test_adjustable_confidence_threshold(self) -> None:
        """Confidence threshold can be adjusted."""
        msg = {"text": "invia one two three"}  # invia is 3 words from end

        # With high threshold, should not trigger
        f_strict = SubmitFilter(confidence_threshold=0.95)
        result = f_strict.process(msg)
        assert result.action == FilterAction.PASS

        # With low threshold, should trigger
        f_lenient = SubmitFilter(confidence_threshold=0.5)
        result = f_lenient.process(msg)
        assert result.action == FilterAction.AUGMENT


class TestPipelineBasics:
    """Test Pipeline basic operations."""

    def test_empty_pipeline_passes_message(self) -> None:
        """Empty pipeline passes message through."""
        p = Pipeline()
        msg = {"text": "hello"}
        result = p.process(msg)
        assert result == [msg]

    def test_pipeline_length(self) -> None:
        """Pipeline length matches filter count."""
        p = Pipeline()
        assert len(p) == 0
        p.add_filter(SubmitFilter())
        assert len(p) == 1

    def test_pipeline_filter_names(self) -> None:
        """Pipeline returns filter names."""
        p = Pipeline()
        p.add_filter(SubmitFilter())
        assert p.filter_names == ["submit_filter"]


class TestPipelineWithFilters:
    """Test Pipeline with filters."""

    def test_single_filter_augments(self) -> None:
        """Single filter can augment message."""
        p = Pipeline([SubmitFilter()])
        msg = {"text": "hello submit"}
        result = p.process(msg)
        assert len(result) == 1
        assert result[0]["x_submit"] is True
        assert result[0]["text"] == "hello"

    def test_message_without_trigger_passes(self) -> None:
        """Message without trigger passes through."""
        p = Pipeline([SubmitFilter()])
        msg = {"text": "hello world"}
        result = p.process(msg)
        assert len(result) == 1
        assert result[0] == msg


class TestPipelineChaining:
    """Test Pipeline filter chaining."""

    def test_filters_chain_in_order(self) -> None:
        """Filters are applied in order."""
        # Create two filters with different triggers
        f1 = SubmitFilter(triggers=[["first"]])
        f2 = SubmitFilter(triggers=[["second"]])

        p = Pipeline([f1, f2])

        # First filter should match
        msg = {"text": "test first"}
        result = p.process(msg)
        assert result[0]["x_submit"] is True

    def test_second_filter_sees_modified_message(self) -> None:
        """Second filter sees message modified by first."""
        # First filter removes "submit" and sets x_submit
        f1 = SubmitFilter(triggers=[["submit"]])
        # Second filter would trigger on "send" but we already have x_submit
        f2 = SubmitFilter(triggers=[["send"]])

        p = Pipeline([f1, f2])
        msg = {"text": "test submit send"}
        result = p.process(msg)

        # First filter sets x_submit, second passes through
        assert result[0]["x_submit"] is True
        # Text should have "submit" removed, but "send" remains
        # (second filter passes because x_submit already True)
        assert "submit" not in result[0]["text"]


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_only_trigger_word(self) -> None:
        """Message with only trigger word results in empty text."""
        f = SubmitFilter()
        msg = {"text": "submit"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["text"] == ""
        assert result.messages[0]["x_submit"] is True

    def test_punctuation_around_trigger(self) -> None:
        """Trigger with punctuation is detected."""
        f = SubmitFilter()
        msg = {"text": "hello, submit!"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_submit"] is True

    def test_non_consecutive_multi_word_trigger(self) -> None:
        """Non-consecutive multi-word trigger has lower confidence."""
        f = SubmitFilter(triggers=[["ok", "invia"]], confidence_threshold=0.7)

        # Consecutive: high confidence
        msg1 = {"text": "test ok invia"}
        result1 = f.process(msg1)
        assert result1.action == FilterAction.AUGMENT

        # Non-consecutive: lower confidence but still passes with low threshold
        msg2 = {"text": "test ok qualcosa invia"}
        result2 = f.process(msg2)
        # With gap_penalty and low threshold (0.7), still triggers
        assert result2.action == FilterAction.AUGMENT

    def test_message_preserves_other_fields(self) -> None:
        """Message preserves other fields when augmented."""
        f = SubmitFilter()
        msg = {"text": "hello submit", "id": "123", "custom": "value"}
        result = f.process(msg)
        assert result.messages[0]["id"] == "123"
        assert result.messages[0]["custom"] == "value"
        assert result.messages[0]["x_submit"] is True
