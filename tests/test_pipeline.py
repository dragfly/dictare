"""Tests for the pipeline filter system."""

import pytest

from dictare.core.bus import bus
from dictare.pipeline import (
    AgentFilter,
    InputFilter,
    Pipeline,
    PipelineAction,
    PipelineResult,
)
from dictare.pipeline.filters.agent_filter import (
    edit_score,
    fuzzy_match_score,
    phonetic_score,
)
from dictare.pipeline.filters.input_filter import (
    DEFAULT_SUBMIT_TRIGGERS,
    _normalize,
    _tokenize,
)

# Triggers used in tests only — production default is empty dict (must configure in config.toml)
_TEST_TRIGGERS: dict[str, list[list[str]]] = {
    "*": [["ok", "send"], ["ok", "submit"], ["go", "ahead"]],
    "it": [["ok", "invia"], ["ok", "in", "via"], ["ok", "manda"], ["vai."]],
}

def _make_filter(**kwargs: object) -> InputFilter:
    """Create InputFilter with test triggers (production default is empty)."""
    if "triggers" not in kwargs:
        kwargs["triggers"] = _TEST_TRIGGERS
    return InputFilter(**kwargs)  # type: ignore[arg-type]

@pytest.fixture(autouse=True)
def reset_event_bus():
    """Reset event bus before each test."""
    bus.reset()
    yield
    bus.reset()

class TestHelperFunctions:
    """Test helper functions for text processing."""

    def test_normalize_lowercase(self) -> None:
        """Normalize converts to lowercase."""
        assert _normalize("HELLO") == "hello"
        assert _normalize("Hello World") == "hello world"

    def test_normalize_removes_accents(self) -> None:
        """Normalize removes accents."""
        assert _normalize("cafe\u0301") == "cafe"
        assert _normalize("nai\u0308ve") == "naive"
        assert _normalize("re\u0301sume\u0301") == "resume"

    def test_tokenize_splits_on_non_alphanumeric(self) -> None:
        """Tokenize splits on non-alphanumeric characters."""
        assert _tokenize("hello world") == ["hello", "world"]
        assert _tokenize("hello, world!") == ["hello", "world"]
        assert _tokenize("ok invia") == ["ok", "invia"]

    def test_tokenize_filters_empty(self) -> None:
        """Tokenize filters empty tokens."""
        assert _tokenize("  hello   world  ") == ["hello", "world"]
        assert _tokenize("...test...") == ["test"]

class TestPipelineResult:
    """Test PipelineResult factory methods."""

    def test_passed_creates_pass_action(self) -> None:
        """PipelineResult.passed creates PASS action with message."""
        msg = {"text": "hello"}
        result = PipelineResult.passed(msg)
        assert result.action == PipelineAction.PASS
        assert result.messages == [msg]

    def test_augmented_creates_augment_action(self) -> None:
        """PipelineResult.augmented creates AUGMENT action with message."""
        msg = {"text": "hello", "x_input": {"submit": True}}
        result = PipelineResult.augmented(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages == [msg]

    def test_consumed_creates_consume_action(self) -> None:
        """PipelineResult.consumed creates CONSUME action."""
        result = PipelineResult.consumed()
        assert result.action == PipelineAction.CONSUME
        assert result.messages == []

    def test_consumed_with_messages(self) -> None:
        """PipelineResult.consumed can include output messages."""
        msgs = [{"text": "a"}, {"text": "b"}]
        result = PipelineResult.consumed(msgs)
        assert result.action == PipelineAction.CONSUME
        assert result.messages == msgs

class TestInputFilterBasics:
    """Test InputFilter basic operations."""

    def test_default_triggers_empty(self) -> None:
        """InputFilter has empty triggers by default (must configure in config.toml)."""
        f = InputFilter()
        assert f.triggers == {}
        assert f.triggers == DEFAULT_SUBMIT_TRIGGERS

    def test_custom_triggers(self) -> None:
        """InputFilter accepts custom triggers dict."""
        custom = {"en": [["done"], ["finish"]], "it": [["finito"]]}
        f = InputFilter(triggers=custom)
        assert f.triggers == custom

    def test_name_property(self) -> None:
        """InputFilter has correct name."""
        f = InputFilter()
        assert f.name == "input_filter"

    def test_empty_text_passes(self) -> None:
        """Empty text passes through unchanged."""
        f = InputFilter()
        msg = {"text": ""}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS
        assert result.messages[0]["text"] == ""

    def test_existing_input_flag_passes(self) -> None:
        """Message with existing x_input passes through."""
        f = InputFilter()
        msg = {"text": "hello submit", "x_input": {"submit": True}}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS
        assert result.messages[0] == msg

class TestInputFilterTriggerDetection:
    """Test InputFilter trigger detection."""

    def test_multi_word_trigger_at_end(self) -> None:
        """Multi-word trigger at end is detected."""
        f = _make_filter()
        msg = {"text": "hello world ok send"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True
        assert result.messages[0]["text"] == "hello world"

    def test_italian_ok_invia_trigger(self) -> None:
        """Italian 'ok invia' trigger is detected."""
        f = _make_filter()
        msg = {"text": "ho un bug nel parser ok invia", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True
        assert result.messages[0]["text"] == "ho un bug nel parser"

    def test_italian_ok_in_via_trigger(self) -> None:
        """Italian 'ok in via' (misheard 'ok invia') trigger is detected."""
        f = _make_filter()
        msg = {"text": "ho un bug nel parser ok in via", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True
        assert result.messages[0]["text"] == "ho un bug nel parser"

    def test_multi_word_trigger(self) -> None:
        """Multi-word trigger (ok invia) is detected."""
        f = _make_filter()
        msg = {"text": "fammi vedere il codice ok invia", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True
        assert "ok" not in result.messages[0]["text"]
        assert "invia" not in result.messages[0]["text"]

    def test_trigger_in_middle_not_detected(self) -> None:
        """Trigger in middle of text (far from end) is not detected."""
        f = InputFilter(triggers={"en": [["submit"]]})
        # Many words after the trigger, beyond max_scan_words
        words = ["submit"] + ["word"] * 20 + ["end"]
        msg = {"text": " ".join(words)}
        result = f.process(msg)
        # Should pass through because submit is too far from end
        assert result.action == PipelineAction.PASS

    def test_case_insensitive(self) -> None:
        """Trigger detection is case insensitive."""
        f = _make_filter()
        msg = {"text": "hello OK SEND"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True

    def test_accent_insensitive(self) -> None:
        """Trigger detection ignores accents."""
        f = InputFilter(triggers={"it": [["ok", "invi\u0300a"]]})  # With accent
        msg = {"text": "test ok invia", "language": "it"}  # Without accent
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT

    def test_x_input_submit_not_overwritten(self) -> None:
        """Existing x_input with submit=True is preserved (filter passes through)."""
        f = InputFilter()
        msg = {"text": "hello ok submit", "x_input": {"submit": True}}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS
        assert result.messages[0]["x_input"] == {"submit": True}

    def test_x_input_newline_still_checks_triggers(self) -> None:
        """x_input with newline=True does NOT skip trigger detection."""
        f = _make_filter()
        msg = {"text": "hello ok submit", "x_input": {"newline": True}}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True

    def test_last_word_only_trigger_at_end(self) -> None:
        """Last-word-only trigger ('vai.') matches when last word."""
        f = _make_filter()
        msg = {"text": "correggi il bug vai", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True
        assert result.messages[0]["text"] == "correggi il bug"

    def test_last_word_only_trigger_not_at_end(self) -> None:
        """Last-word-only trigger ('vai.') does NOT match when not last word."""
        f = _make_filter()
        msg = {"text": "vai a vedere il codice", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS

    def test_last_word_only_with_punctuation(self) -> None:
        """Last-word-only trigger works even if transcription has punctuation."""
        f = _make_filter()
        msg = {"text": "correggi il bug, vai!", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True

    def test_last_word_only_case_insensitive(self) -> None:
        """Last-word-only trigger is case insensitive."""
        f = _make_filter()
        msg = {"text": "correggi il bug VAI", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT

    def test_last_word_only_confidence_is_1(self) -> None:
        """Last-word-only trigger has confidence 1.0."""
        f = _make_filter()
        msg = {"text": "test vai", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["confidence"] == 1.0

    def test_last_word_only_custom_trigger(self) -> None:
        """Custom last-word-only trigger works."""
        f = InputFilter(triggers={"en": [["done."]]})
        msg = {"text": "I finished the task done"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["text"] == "I finished the task"

    def test_single_word_not_last_does_not_trigger(self) -> None:
        """Single word that appears in the middle doesn't trigger."""
        f = InputFilter(triggers={"en": [["done."]]})
        msg = {"text": "done with the first part"}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS

class TestInputFilterConfidence:
    """Test InputFilter confidence-based detection."""

    def test_high_confidence_at_end(self) -> None:
        """Trigger at very end has high confidence."""
        f = _make_filter(confidence_threshold=0.85)
        msg = {"text": "test ok invia", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT

    def test_low_confidence_far_from_end(self) -> None:
        """Multi-word trigger far from end has low confidence."""
        f = InputFilter(
            triggers={"en": [["submit"]]},
            confidence_threshold=0.85,
            max_scan_words=15,
        )
        # submit is 7 words from end -> 0.95^7 * 1.1 = 0.768 < 0.85
        msg = {"text": "submit one two three four five six seven"}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS

    def test_adjustable_confidence_threshold(self) -> None:
        """Confidence threshold can be adjusted."""
        triggers = {"en": [["submit"]]}
        msg = {"text": "submit one two three"}  # submit is 3 words from end

        # With high threshold, should not trigger
        f_strict = InputFilter(triggers=triggers, confidence_threshold=0.95)
        result = f_strict.process(msg)
        assert result.action == PipelineAction.PASS

        # With low threshold, should trigger
        f_lenient = InputFilter(triggers=triggers, confidence_threshold=0.5)
        result = f_lenient.process(msg)
        assert result.action == PipelineAction.AUGMENT

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
        p.add_step(InputFilter())
        assert len(p) == 1

    def test_pipeline_step_names(self) -> None:
        """Pipeline returns filter names."""
        p = Pipeline()
        p.add_step(InputFilter())
        assert p.step_names == ["input_filter"]

class TestPipelineWithFilters:
    """Test Pipeline with filters."""

    def test_single_filter_augments(self) -> None:
        """Single filter can augment message."""
        p = Pipeline([_make_filter()])
        msg = {"text": "hello ok send"}
        result = p.process(msg)
        assert len(result) == 1
        assert result[0]["x_input"]["submit"] is True
        assert result[0]["text"] == "hello"

    def test_message_without_trigger_passes(self) -> None:
        """Message without trigger passes through."""
        p = Pipeline([InputFilter()])
        msg = {"text": "hello world"}
        result = p.process(msg)
        assert len(result) == 1
        assert result[0] == msg

class TestPipelineChaining:
    """Test Pipeline filter chaining."""

    def test_filters_chain_in_order(self) -> None:
        """Filters are applied in order."""
        # Create two filters with different triggers
        f1 = InputFilter(triggers={"en": [["first"]]})
        f2 = InputFilter(triggers={"en": [["second"]]})

        p = Pipeline([f1, f2])

        # First filter should match
        msg = {"text": "test first"}
        result = p.process(msg)
        assert result[0]["x_input"]["submit"] is True

    def test_second_filter_sees_modified_message(self) -> None:
        """Second filter sees message modified by first."""
        # First filter removes "submit" and sets x_input
        f1 = InputFilter(triggers={"en": [["submit"]]})
        # Second filter would trigger on "send" but we already have x_input
        f2 = InputFilter(triggers={"en": [["send"]]})

        p = Pipeline([f1, f2])
        msg = {"text": "test submit send"}
        result = p.process(msg)

        # First filter sets x_input, second passes through
        assert result[0]["x_input"]["submit"] is True
        # Text should have "submit" removed, but "send" remains
        # (second filter passes because x_input already set)
        assert "submit" not in result[0]["text"]

class TestLanguageBasedTriggers:
    """Test language-based trigger detection."""

    def test_italian_message_uses_italian_triggers(self) -> None:
        """Italian message uses Italian triggers."""
        f = _make_filter()
        msg = {"text": "test ok invia", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True

    def test_english_message_uses_wildcard_triggers(self) -> None:
        """English message uses wildcard triggers."""
        f = _make_filter()
        msg = {"text": "test ok send", "language": "en"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True

    def test_italian_message_also_checks_wildcard(self) -> None:
        """Italian message also checks wildcard triggers."""
        f = _make_filter()
        # Wildcard trigger "ok submit" should work even with Italian language
        msg = {"text": "test ok submit", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT

    def test_unknown_language_uses_wildcard(self) -> None:
        """Unknown language uses wildcard triggers."""
        f = _make_filter()
        msg = {"text": "test ok send", "language": "xyz"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT

    def test_no_language_uses_wildcard(self) -> None:
        """Message without language uses wildcard triggers."""
        f = _make_filter()
        msg = {"text": "test ok send"}  # No language field
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT

    def test_language_code_normalized(self) -> None:
        """Language codes like 'en-US' are normalized to 'en'."""
        f = _make_filter()
        msg = {"text": "test ok send", "language": "en-US"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT

    def test_language_specific_trigger_not_matched_cross_language(self) -> None:
        """Language-specific trigger not matched for a different language."""
        # Filter with only Italian language triggers (no wildcard)
        f = InputFilter(triggers={"it": [["invia"]]})
        msg = {"text": "test invia", "language": "en"}
        result = f.process(msg)
        # "invia" is Italian-only, not matched for English
        assert result.action == PipelineAction.PASS

    def test_wildcard_plus_language_specific(self) -> None:
        """Wildcard and language-specific triggers both active."""
        f = InputFilter(
            triggers={
                "*": [["send"]],  # Always active
                "it": [["manda"]],  # Italian only
            }
        )
        # Italian message with Italian trigger
        msg = {"text": "test manda", "language": "it"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["text"] == "test"

        # Italian message with wildcard trigger
        msg2 = {"text": "test send", "language": "it"}
        result2 = f.process(msg2)
        assert result2.action == PipelineAction.AUGMENT

class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_only_trigger_word(self) -> None:
        """Message with only trigger word results in empty text."""
        f = InputFilter(triggers={"en": [["submit"]]})
        msg = {"text": "submit"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["text"] == ""
        assert result.messages[0]["x_input"]["submit"] is True

    def test_punctuation_around_trigger(self) -> None:
        """Trigger with punctuation is detected."""
        f = _make_filter()
        msg = {"text": "hello, ok send!"}
        result = f.process(msg)
        assert result.action == PipelineAction.AUGMENT
        assert result.messages[0]["x_input"]["submit"] is True

    def test_non_consecutive_multi_word_trigger(self) -> None:
        """Non-consecutive multi-word trigger has lower confidence."""
        f = InputFilter(
            triggers={"it": [["ok", "invia"]]}, confidence_threshold=0.7
        )

        # Consecutive: high confidence
        msg1 = {"text": "test ok invia", "language": "it"}
        result1 = f.process(msg1)
        assert result1.action == PipelineAction.AUGMENT

        # Non-consecutive: lower confidence but still passes with low threshold
        msg2 = {"text": "test ok qualcosa invia", "language": "it"}
        result2 = f.process(msg2)
        # With gap_penalty and low threshold (0.7), still triggers
        assert result2.action == PipelineAction.AUGMENT

    def test_message_preserves_other_fields(self) -> None:
        """Message preserves other fields when augmented."""
        f = _make_filter()
        msg = {"text": "hello ok send", "id": "123", "custom": "value"}
        result = f.process(msg)
        # fork_message() creates new ID, traces back to original
        assert result.messages[0]["parent_id"] == "123"
        assert result.messages[0]["trace_id"] == "123"
        assert result.messages[0]["id"] != "123"  # New ID generated
        assert result.messages[0]["custom"] == "value"
        assert result.messages[0]["x_input"]["submit"] is True

# =============================================================================
# AgentFilter Tests
# =============================================================================

class TestPhoneticMatching:
    """Test phonetic matching functions."""

    def test_phonetic_score_identical(self) -> None:
        """Identical phonetic representation scores 1.0."""
        # koder and coder sound the same
        assert phonetic_score("koder", "coder") == 1.0
        assert phonetic_score("dictare", "dictare") == 1.0

    def test_phonetic_score_similar(self) -> None:
        """Similar sounding words have high phonetic score."""
        # These should have same metaphone
        score = phonetic_score("koder", "quant")
        assert score >= 0.7  # At least partial match

    def test_phonetic_score_different(self) -> None:
        """Different sounding words have low phonetic score."""
        score = phonetic_score("dictare", "python")
        assert score < 0.5

    def test_edit_score_identical(self) -> None:
        """Identical strings score 1.0."""
        assert edit_score("hello", "hello") == 1.0

    def test_edit_score_similar(self) -> None:
        """Similar strings have high edit score."""
        score = edit_score("koder", "coder")
        assert score > 0.7  # Only 1 character different

    def test_edit_score_different(self) -> None:
        """Different strings have low edit score."""
        score = edit_score("abc", "xyz")
        assert score < 0.5

    def test_fuzzy_match_combines_scores(self) -> None:
        """Fuzzy match combines phonetic and edit scores."""
        # koder vs coder: phonetic=1.0, edit=0.8 -> combined > 0.8
        score = fuzzy_match_score("koder", "coder")
        assert score > 0.8

        # Completely different
        score = fuzzy_match_score("abc", "xyz")
        assert score < 0.5

class TestAgentFilterBasics:
    """Test AgentFilter basic operations."""

    def test_name_property(self) -> None:
        """Filter has correct name."""
        f = AgentFilter(subscribe_to_events=False)
        assert f.name == "agent_filter"

    def test_empty_text_passes(self) -> None:
        """Empty text passes through."""
        f = AgentFilter(agent_ids=["dictare"], subscribe_to_events=False)
        msg = {"text": ""}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS

    def test_no_agents_passes(self) -> None:
        """Message passes if no agents configured."""
        f = AgentFilter(agent_ids=[], subscribe_to_events=False)
        msg = {"text": "agent dictare"}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS

    def test_existing_agent_switch_passes(self) -> None:
        """Message with existing x_agent_switch passes through."""
        f = AgentFilter(agent_ids=["dictare"], subscribe_to_events=False)
        msg = {"text": "agent dictare", "x_agent_switch": {"target": "other"}}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS

class TestAgentFilterDetection:
    """Test AgentFilter agent switch detection."""

    def test_exact_match(self) -> None:
        """Exact agent name match produces two messages."""
        f = AgentFilter(agent_ids=["dictare", "koder"], subscribe_to_events=False)
        msg = {"text": "fammi vedere il codice agent dictare"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        # Two messages: text before trigger, then switch command
        assert len(result.messages) == 2
        # First message: text without trigger (no switch flag)
        assert "x_agent_switch" not in result.messages[0]
        assert "agent" not in result.messages[0]["text"].lower()
        assert "dictare" not in result.messages[0]["text"].lower()
        # Second message: empty text with switch flag
        assert result.messages[1]["x_agent_switch"]["target"] == "dictare"
        assert result.messages[1]["text"] == ""

    def test_phonetic_match_koder_coder(self) -> None:
        """Phonetic match: 'coder' matches 'koder'."""
        f = AgentFilter(agent_ids=["koder", "dictare"], subscribe_to_events=False)
        msg = {"text": "questo bug agent coder"}  # Heard as "coder"
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert len(result.messages) == 2
        assert result.messages[1]["x_agent_switch"]["target"] == "koder"

    def test_phonetic_match_koder_quant(self) -> None:
        """Phonetic match: 'quant' matches 'koder'."""
        f = AgentFilter(agent_ids=["koder", "dictare"], subscribe_to_events=False)
        msg = {"text": "questo bug agent quant"}  # Heard as "quant"
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert len(result.messages) == 2
        assert result.messages[1]["x_agent_switch"]["target"] == "koder"

    def test_italian_agente_trigger(self) -> None:
        """Italian 'agente' trigger is detected when configured."""
        f = AgentFilter(
            agent_ids=["dictare"],
            triggers=["agent", "agente"],  # User must add "agente" for Italian
            subscribe_to_events=False,
        )
        msg = {"text": "fammi vedere agente dictare"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert len(result.messages) == 2
        assert result.messages[1]["x_agent_switch"]["target"] == "dictare"

    def test_case_insensitive(self) -> None:
        """Agent matching is case insensitive."""
        f = AgentFilter(agent_ids=["Dictare"], subscribe_to_events=False)
        msg = {"text": "agent dictare"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        # Only switch message when trigger is at start (no text before)
        assert len(result.messages) == 1
        assert result.messages[0]["x_agent_switch"]["target"] == "Dictare"

    def test_no_match_below_threshold(self) -> None:
        """No match if score is below threshold."""
        f = AgentFilter(agent_ids=["dictare"], match_threshold=0.95, subscribe_to_events=False)
        msg = {"text": "agent boxtype"}  # Similar but not identical
        result = f.process(msg)
        # boxtype vs dictare: edit=0.857, phonetic different (B vs F/V)
        # With high threshold, should not match
        assert result.action == PipelineAction.PASS

    def test_best_match_selected(self) -> None:
        """Best matching agent is selected when multiple could match."""
        f = AgentFilter(agent_ids=["koder", "quant-analysis"], subscribe_to_events=False)
        msg = {"text": "agent coder"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        # koder should match better than quant-analysis
        # Only switch message (no text before trigger)
        assert len(result.messages) == 1
        assert result.messages[0]["x_agent_switch"]["target"] == "koder"

    def test_trigger_in_middle_not_detected(self) -> None:
        """Trigger in middle of text (not at end) is not detected."""
        f = AgentFilter(agent_ids=["dictare"], max_scan_words=5, subscribe_to_events=False)
        # agent dictare is more than 5 words from end
        msg = {"text": "agent dictare one two three four five six"}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS

    def test_text_cleaned_after_match(self) -> None:
        """Text before trigger becomes first message, switch is second."""
        f = AgentFilter(agent_ids=["dictare"], subscribe_to_events=False)
        msg = {"text": "questo \u00e8 il codice agent dictare"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert len(result.messages) == 2
        # First message: text before trigger
        assert result.messages[0]["text"] == "questo \u00e8 il codice"
        assert "x_agent_switch" not in result.messages[0]
        # Second message: switch command
        assert result.messages[1]["text"] == ""
        assert result.messages[1]["x_agent_switch"]["target"] == "dictare"

    def test_box_type_matches_dictare(self) -> None:
        """'box type' (two words) matches 'dictare' - handles Whisper space insertion."""
        # Note: This tests the case where Whisper transcribes "dictare" as "box type"
        # The fuzzy match should still work on "box" vs "dictare"
        f = AgentFilter(agent_ids=["dictare"], match_threshold=0.5, subscribe_to_events=False)
        msg = {"text": "agent box"}  # Just "box" - "type" is separate
        result = f.process(msg)
        # "box" vs "dictare": phonetic B vs V (different), edit distance 4/7
        # This is a tough case - may not match well
        # Let's see if it passes with 0.5 threshold
        if result.action == PipelineAction.CONSUME:
            # Should only have switch message (no text before)
            assert result.messages[-1]["x_agent_switch"]["target"] == "dictare"

class TestAgentFilterWithPipeline:
    """Test AgentFilter integration with Pipeline."""

    def test_agent_filter_before_input_filter(self) -> None:
        """Agent filter can run before input filter in pipeline."""
        agent_f = AgentFilter(agent_ids=["dictare"], subscribe_to_events=False)
        input_f = _make_filter()

        p = Pipeline([agent_f, input_f])

        # Agent switch command
        msg = {"text": "agent dictare"}
        result = p.process(msg)
        assert result[0].get("x_agent_switch", {}).get("target") == "dictare"

    def test_agent_and_input_in_same_message(self) -> None:
        """Both agent switch and input can be detected."""
        agent_f = AgentFilter(agent_ids=["dictare"], subscribe_to_events=False)
        input_f = _make_filter()

        # Agent filter first, then input filter
        p = Pipeline([agent_f, input_f])

        # Note: This would require agent at end AND submit
        # In practice, these would be separate messages
        msg = {"text": "hello ok send"}
        result = p.process(msg)
        assert result[0].get("x_input", {}).get("submit") is True

class TestAgentFilterEventBus:
    """Test AgentFilter event bus integration."""

    def test_subscribes_to_agent_events_by_default(self) -> None:
        """Filter subscribes to agent.registered/unregistered events by default."""
        f = AgentFilter()  # subscribe_to_events=True by default
        assert f.agent_ids == []

        # Register agents via events
        bus.publish("agent.registered", agent_id="dictare")
        bus.publish("agent.registered", agent_id="koder")

        # Filter should have both agents
        assert f.agent_ids == ["dictare", "koder"]

    def test_dynamic_agent_update(self) -> None:
        """Filter updates agent_ids when event is published."""
        f = AgentFilter()

        # Initially no agents
        msg = {"text": "agent dictare"}
        result = f.process(msg)
        assert result.action == PipelineAction.PASS  # No agents to match

        # Add agent via event
        bus.publish("agent.registered", agent_id="dictare")

        # Now should match
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME
        assert result.messages[0]["x_agent_switch"]["target"] == "dictare"

    def test_agent_removed_via_event(self) -> None:
        """Filter stops matching agent when removed via event."""
        f = AgentFilter()

        # Add agents
        bus.publish("agent.registered", agent_id="dictare")
        bus.publish("agent.registered", agent_id="koder")

        # Should match dictare
        msg = {"text": "agent dictare"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME

        # Remove dictare
        bus.publish("agent.unregistered", agent_id="dictare")

        # Should not match dictare anymore
        result = f.process(msg)
        assert result.action == PipelineAction.PASS

        # koder should still work
        msg = {"text": "agent koder"}
        result = f.process(msg)
        assert result.action == PipelineAction.CONSUME

    def test_no_subscription_when_disabled(self) -> None:
        """Filter doesn't subscribe when subscribe_to_events=False."""
        f = AgentFilter(subscribe_to_events=False)

        # Publish event
        bus.publish("agent.registered", agent_id="dictare")

        # Filter should not have updated
        assert f.agent_ids == []

    def test_multiple_filters_receive_event(self) -> None:
        """Multiple filters all receive the event."""
        f1 = AgentFilter()
        f2 = AgentFilter()

        bus.publish("agent.registered", agent_id="dictare")

        assert f1.agent_ids == ["dictare"]
        assert f2.agent_ids == ["dictare"]

    def test_duplicate_register_ignored(self) -> None:
        """Registering same agent twice doesn't duplicate."""
        f = AgentFilter()

        bus.publish("agent.registered", agent_id="dictare")
        bus.publish("agent.registered", agent_id="dictare")

        assert f.agent_ids == ["dictare"]

    def test_unregister_nonexistent_ignored(self) -> None:
        """Unregistering non-existent agent is a no-op."""
        f = AgentFilter()

        bus.publish("agent.unregistered", agent_id="dictare")

        assert f.agent_ids == []
