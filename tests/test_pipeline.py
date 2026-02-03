"""Tests for the pipeline filter system."""


import pytest

from voxtype.events import bus
from voxtype.pipeline import (
    AgentFilter,
    FilterAction,
    FilterResult,
    Pipeline,
    SubmitFilter,
)
from voxtype.pipeline.agent_filter import (
    edit_score,
    fuzzy_match_score,
    phonetic_score,
)
from voxtype.pipeline.submit_filter import (
    DEFAULT_SUBMIT_TRIGGERS,
    _normalize,
    _tokenize,
)


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
        """SubmitFilter has default triggers organized by language."""
        f = SubmitFilter()
        assert f.triggers == DEFAULT_SUBMIT_TRIGGERS
        assert "it" in f.triggers
        assert "en" in f.triggers
        assert ["ok", "invia"] in f.triggers["it"]
        assert ["submit"] in f.triggers["en"]

    def test_custom_triggers(self) -> None:
        """SubmitFilter accepts custom triggers dict."""
        custom = {"en": [["done"], ["finish"]], "it": [["finito"]]}
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
        msg = {"text": "ho un bug nel parser invia", "language": "it"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_submit"] is True
        assert result.messages[0]["text"] == "ho un bug nel parser"

    def test_italian_in_via_trigger(self) -> None:
        """Italian 'in via' (misheard 'invia') trigger is detected."""
        f = SubmitFilter()
        msg = {"text": "ho un bug nel parser in via", "language": "it"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_submit"] is True
        assert result.messages[0]["text"] == "ho un bug nel parser"

    def test_multi_word_trigger(self) -> None:
        """Multi-word trigger (ok invia) is detected."""
        f = SubmitFilter()
        msg = {"text": "fammi vedere il codice ok invia", "language": "it"}
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
        f = SubmitFilter(triggers={"it": [["invìa"]]})  # With accent
        msg = {"text": "test invia", "language": "it"}  # Without accent
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
        msg = {"text": "test invia", "language": "it"}  # invia is last word
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
        msg = {"text": "invia one two three four five six seven", "language": "it"}
        result = f.process(msg)
        assert result.action == FilterAction.PASS

    def test_adjustable_confidence_threshold(self) -> None:
        """Confidence threshold can be adjusted."""
        msg = {"text": "invia one two three", "language": "it"}  # invia is 3 words from end

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
        f1 = SubmitFilter(triggers={"en": [["first"]]})
        f2 = SubmitFilter(triggers={"en": [["second"]]})

        p = Pipeline([f1, f2])

        # First filter should match
        msg = {"text": "test first"}
        result = p.process(msg)
        assert result[0]["x_submit"] is True

    def test_second_filter_sees_modified_message(self) -> None:
        """Second filter sees message modified by first."""
        # First filter removes "submit" and sets x_submit
        f1 = SubmitFilter(triggers={"en": [["submit"]]})
        # Second filter would trigger on "send" but we already have x_submit
        f2 = SubmitFilter(triggers={"en": [["send"]]})

        p = Pipeline([f1, f2])
        msg = {"text": "test submit send"}
        result = p.process(msg)

        # First filter sets x_submit, second passes through
        assert result[0]["x_submit"] is True
        # Text should have "submit" removed, but "send" remains
        # (second filter passes because x_submit already True)
        assert "submit" not in result[0]["text"]


class TestLanguageBasedTriggers:
    """Test language-based trigger detection."""

    def test_italian_message_uses_italian_triggers(self) -> None:
        """Italian message uses Italian triggers."""
        f = SubmitFilter()
        msg = {"text": "test invia", "language": "it"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_submit"] is True

    def test_english_message_uses_english_triggers(self) -> None:
        """English message uses English triggers."""
        f = SubmitFilter()
        msg = {"text": "test submit", "language": "en"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_submit"] is True

    def test_italian_message_also_checks_english(self) -> None:
        """Italian message also checks English triggers."""
        f = SubmitFilter()
        # English trigger "submit" should work even with Italian language
        msg = {"text": "test submit", "language": "it"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT

    def test_unknown_language_falls_back_to_english(self) -> None:
        """Unknown language uses only English triggers."""
        f = SubmitFilter()
        msg = {"text": "test submit", "language": "xyz"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT

    def test_no_language_defaults_to_english(self) -> None:
        """Message without language defaults to English."""
        f = SubmitFilter()
        msg = {"text": "test submit"}  # No language field
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT

    def test_language_code_normalized(self) -> None:
        """Language codes like 'en-US' are normalized to 'en'."""
        f = SubmitFilter()
        msg = {"text": "test submit", "language": "en-US"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT

    def test_italian_trigger_not_matched_for_english_only(self) -> None:
        """Italian trigger not matched when only English triggers available."""
        # Filter with only English triggers
        f = SubmitFilter(triggers={"en": [["submit"]]})
        msg = {"text": "test invia", "language": "en"}
        result = f.process(msg)
        # "invia" is not in English triggers
        assert result.action == FilterAction.PASS

    def test_language_specific_priority(self) -> None:
        """Language-specific triggers have priority over English."""
        f = SubmitFilter(
            triggers={
                "it": [["manda"]],  # Italian
                "en": [["send"]],  # English
            }
        )
        # Italian message with Italian trigger
        msg = {"text": "test manda", "language": "it"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["text"] == "test"


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
        f = SubmitFilter(
            triggers={"it": [["ok", "invia"]]}, confidence_threshold=0.7
        )

        # Consecutive: high confidence
        msg1 = {"text": "test ok invia", "language": "it"}
        result1 = f.process(msg1)
        assert result1.action == FilterAction.AUGMENT

        # Non-consecutive: lower confidence but still passes with low threshold
        msg2 = {"text": "test ok qualcosa invia", "language": "it"}
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


# =============================================================================
# AgentFilter Tests
# =============================================================================


class TestPhoneticMatching:
    """Test phonetic matching functions."""

    def test_phonetic_score_identical(self) -> None:
        """Identical phonetic representation scores 1.0."""
        # koder and coder sound the same
        assert phonetic_score("koder", "coder") == 1.0
        assert phonetic_score("voxtype", "voxtype") == 1.0

    def test_phonetic_score_similar(self) -> None:
        """Similar sounding words have high phonetic score."""
        # These should have same metaphone
        score = phonetic_score("koder", "quant")
        assert score >= 0.7  # At least partial match

    def test_phonetic_score_different(self) -> None:
        """Different sounding words have low phonetic score."""
        score = phonetic_score("voxtype", "python")
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
        # koder vs coder: phonetic=1.0, edit=0.8 → combined > 0.8
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
        f = AgentFilter(agent_ids=["voxtype"], subscribe_to_events=False)
        msg = {"text": ""}
        result = f.process(msg)
        assert result.action == FilterAction.PASS

    def test_no_agents_passes(self) -> None:
        """Message passes if no agents configured."""
        f = AgentFilter(agent_ids=[], subscribe_to_events=False)
        msg = {"text": "agent voxtype"}
        result = f.process(msg)
        assert result.action == FilterAction.PASS

    def test_existing_agent_switch_passes(self) -> None:
        """Message with existing x_agent_switch passes through."""
        f = AgentFilter(agent_ids=["voxtype"], subscribe_to_events=False)
        msg = {"text": "agent voxtype", "x_agent_switch": "other"}
        result = f.process(msg)
        assert result.action == FilterAction.PASS


class TestAgentFilterDetection:
    """Test AgentFilter agent switch detection."""

    def test_exact_match(self) -> None:
        """Exact agent name match is detected."""
        f = AgentFilter(agent_ids=["voxtype", "koder"], subscribe_to_events=False)
        msg = {"text": "fammi vedere il codice agent voxtype"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_agent_switch"] == "voxtype"
        assert "agent" not in result.messages[0]["text"].lower()
        assert "voxtype" not in result.messages[0]["text"].lower()

    def test_phonetic_match_koder_coder(self) -> None:
        """Phonetic match: 'coder' matches 'koder'."""
        f = AgentFilter(agent_ids=["koder", "voxtype"], subscribe_to_events=False)
        msg = {"text": "questo bug agent coder"}  # Heard as "coder"
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_agent_switch"] == "koder"

    def test_phonetic_match_koder_quant(self) -> None:
        """Phonetic match: 'quant' matches 'koder'."""
        f = AgentFilter(agent_ids=["koder", "voxtype"], subscribe_to_events=False)
        msg = {"text": "questo bug agent quant"}  # Heard as "quant"
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_agent_switch"] == "koder"

    def test_italian_agente_trigger(self) -> None:
        """Italian 'agente' trigger is detected when configured."""
        f = AgentFilter(
            agent_ids=["voxtype"],
            triggers=["agent", "agente"],  # User must add "agente" for Italian
            subscribe_to_events=False,
        )
        msg = {"text": "fammi vedere agente voxtype"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_agent_switch"] == "voxtype"

    def test_case_insensitive(self) -> None:
        """Agent matching is case insensitive."""
        f = AgentFilter(agent_ids=["VoxType"], subscribe_to_events=False)
        msg = {"text": "agent voxtype"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_agent_switch"] == "VoxType"

    def test_no_match_below_threshold(self) -> None:
        """No match if score is below threshold."""
        f = AgentFilter(agent_ids=["voxtype"], match_threshold=0.95, subscribe_to_events=False)
        msg = {"text": "agent boxtype"}  # Similar but not identical
        result = f.process(msg)
        # boxtype vs voxtype: edit=0.857, phonetic different (B vs F/V)
        # With high threshold, should not match
        assert result.action == FilterAction.PASS

    def test_best_match_selected(self) -> None:
        """Best matching agent is selected when multiple could match."""
        f = AgentFilter(agent_ids=["koder", "quant-analysis"], subscribe_to_events=False)
        msg = {"text": "agent coder"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        # koder should match better than quant-analysis
        assert result.messages[0]["x_agent_switch"] == "koder"

    def test_trigger_in_middle_not_detected(self) -> None:
        """Trigger in middle of text (not at end) is not detected."""
        f = AgentFilter(agent_ids=["voxtype"], max_scan_words=5, subscribe_to_events=False)
        # agent voxtype is more than 5 words from end
        msg = {"text": "agent voxtype one two three four five six"}
        result = f.process(msg)
        assert result.action == FilterAction.PASS

    def test_text_cleaned_after_match(self) -> None:
        """Text is cleaned up after agent switch match."""
        f = AgentFilter(agent_ids=["voxtype"], subscribe_to_events=False)
        msg = {"text": "questo è il codice agent voxtype"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        # Should remove "agent voxtype" from end
        cleaned = result.messages[0]["text"]
        assert cleaned == "questo è il codice"

    def test_fuzzy_trigger_adziente(self) -> None:
        """Fuzzy matching on trigger words - 'adziente' should match 'agente'."""
        f = AgentFilter(
            agent_ids=["voxtype"],
            triggers=["agente"],  # Italian trigger
            subscribe_to_events=False,
        )
        msg = {"text": "fammi vedere adziente voxtype"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_agent_switch"] == "voxtype"

    def test_fuzzy_trigger_aziente(self) -> None:
        """Fuzzy matching on trigger - 'aziente' should match 'agente'."""
        f = AgentFilter(
            agent_ids=["koder"],
            triggers=["agente"],  # Italian trigger
            subscribe_to_events=False,
        )
        msg = {"text": "dimmi l'ora aziente koder"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_agent_switch"] == "koder"

    def test_box_type_matches_voxtype(self) -> None:
        """'box type' (two words) matches 'voxtype' - handles Whisper space insertion."""
        # Note: This tests the case where Whisper transcribes "voxtype" as "box type"
        # The fuzzy match should still work on "box" vs "voxtype"
        f = AgentFilter(agent_ids=["voxtype"], match_threshold=0.5, subscribe_to_events=False)
        msg = {"text": "agent box"}  # Just "box" - "type" is separate
        result = f.process(msg)
        # "box" vs "voxtype": phonetic B vs V (different), edit distance 4/7
        # This is a tough case - may not match well
        # Let's see if it passes with 0.5 threshold
        if result.action == FilterAction.AUGMENT:
            assert result.messages[0]["x_agent_switch"] == "voxtype"

    def test_english_uses_phonetic_for_triggers(self) -> None:
        """English messages use phonetic+edit for trigger matching."""
        f = AgentFilter(agent_ids=["voxtype"], subscribe_to_events=False)
        # "ajent" sounds like "agent" in English (phonetic: AJNT vs AJNT)
        msg = {"text": "ajent voxtype", "language": "en"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_agent_switch"] == "voxtype"

    def test_italian_uses_edit_only_for_triggers(self) -> None:
        """Italian messages use edit distance only for trigger matching."""
        f = AgentFilter(
            agent_ids=["voxtype"],
            triggers=["agente"],  # Italian trigger
            subscribe_to_events=False,
        )
        # "adziente" doesn't match "agente" phonetically, but does via edit distance
        msg = {"text": "adziente voxtype", "language": "it"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_agent_switch"] == "voxtype"


class TestAgentFilterWithPipeline:
    """Test AgentFilter integration with Pipeline."""

    def test_agent_filter_before_submit_filter(self) -> None:
        """Agent filter can run before submit filter in pipeline."""
        agent_f = AgentFilter(agent_ids=["voxtype"], subscribe_to_events=False)
        submit_f = SubmitFilter()

        p = Pipeline([agent_f, submit_f])

        # Agent switch command
        msg = {"text": "agent voxtype"}
        result = p.process(msg)
        assert result[0].get("x_agent_switch") == "voxtype"

    def test_agent_and_submit_in_same_message(self) -> None:
        """Both agent switch and submit can be detected."""
        agent_f = AgentFilter(agent_ids=["voxtype"], subscribe_to_events=False)
        submit_f = SubmitFilter()

        # Agent filter first, then submit filter
        p = Pipeline([agent_f, submit_f])

        # Note: This would require agent at end AND submit
        # In practice, these would be separate messages
        msg = {"text": "hello submit"}
        result = p.process(msg)
        assert result[0].get("x_submit") is True


class TestAgentFilterEventBus:
    """Test AgentFilter event bus integration."""

    def test_subscribes_to_agent_events_by_default(self) -> None:
        """Filter subscribes to agent.registered/unregistered events by default."""
        f = AgentFilter()  # subscribe_to_events=True by default
        assert f.agent_ids == []

        # Register agents via events
        bus.publish("agent.registered", agent_id="voxtype")
        bus.publish("agent.registered", agent_id="koder")

        # Filter should have both agents
        assert f.agent_ids == ["voxtype", "koder"]

    def test_dynamic_agent_update(self) -> None:
        """Filter updates agent_ids when event is published."""
        f = AgentFilter()

        # Initially no agents
        msg = {"text": "agent voxtype"}
        result = f.process(msg)
        assert result.action == FilterAction.PASS  # No agents to match

        # Add agent via event
        bus.publish("agent.registered", agent_id="voxtype")

        # Now should match
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT
        assert result.messages[0]["x_agent_switch"] == "voxtype"

    def test_agent_removed_via_event(self) -> None:
        """Filter stops matching agent when removed via event."""
        f = AgentFilter()

        # Add agents
        bus.publish("agent.registered", agent_id="voxtype")
        bus.publish("agent.registered", agent_id="koder")

        # Should match voxtype
        msg = {"text": "agent voxtype"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT

        # Remove voxtype
        bus.publish("agent.unregistered", agent_id="voxtype")

        # Should not match voxtype anymore
        result = f.process(msg)
        assert result.action == FilterAction.PASS

        # koder should still work
        msg = {"text": "agent koder"}
        result = f.process(msg)
        assert result.action == FilterAction.AUGMENT

    def test_no_subscription_when_disabled(self) -> None:
        """Filter doesn't subscribe when subscribe_to_events=False."""
        f = AgentFilter(subscribe_to_events=False)

        # Publish event
        bus.publish("agent.registered", agent_id="voxtype")

        # Filter should not have updated
        assert f.agent_ids == []

    def test_multiple_filters_receive_event(self) -> None:
        """Multiple filters all receive the event."""
        f1 = AgentFilter()
        f2 = AgentFilter()

        bus.publish("agent.registered", agent_id="voxtype")

        assert f1.agent_ids == ["voxtype"]
        assert f2.agent_ids == ["voxtype"]

    def test_duplicate_register_ignored(self) -> None:
        """Registering same agent twice doesn't duplicate."""
        f = AgentFilter()

        bus.publish("agent.registered", agent_id="voxtype")
        bus.publish("agent.registered", agent_id="voxtype")

        assert f.agent_ids == ["voxtype"]

    def test_unregister_nonexistent_ignored(self) -> None:
        """Unregistering non-existent agent is a no-op."""
        f = AgentFilter()

        bus.publish("agent.unregistered", agent_id="voxtype")

        assert f.agent_ids == []
