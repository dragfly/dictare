"""Voice mute/listen filter.

Detects mute/listen trigger words to toggle voice muting.
When muted, all transcribed text is silently discarded except
for listen triggers that unmute.

This is NOT the OFF state. The engine stays in LISTENING, VAD+STT
keep running, but the filter discards output until "OK listen".

Pattern format is identical to InputFilter triggers:
- Multi-word: ["ok", "mute"] - position-weighted confidence
- Alternatives: ["ok|okay", "mute|stop"] - "|" means OR within each slot
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from dictare.pipeline.base import PipelineResult, fork_message
from dictare.pipeline.filters._text import (
    find_best_match,
    get_triggers_for_message,
)
from dictare.pipeline.filters._text import (
    tokenize as _tokenize,
)

logger = logging.getLogger(__name__)

@dataclass
class MuteFilter:
    """Filter that detects mute/listen voice commands.

    When a mute trigger is detected: CONSUME + emit x_mute message.
    When a listen trigger is detected while muted: CONSUME + emit x_mute message.
    When muted and no listen trigger: CONSUME silently (discard).
    When not muted and no mute trigger: PASS (normal flow).

    Attributes:
        mute_triggers: Trigger patterns to mute (by language).
        listen_triggers: Trigger patterns to unmute (by language).
        is_muted: Injected callback that returns current mute state.
        confidence_threshold: Minimum confidence to trigger (0.0-1.0).
        max_scan_words: Maximum words from end to scan.
        decay_rate: Confidence decay rate per word from end.
    """

    mute_triggers: dict[str, list[list[str]]] = field(default_factory=dict)
    listen_triggers: dict[str, list[list[str]]] = field(default_factory=dict)
    is_muted: Callable[[], bool] = field(default=lambda: False)
    confidence_threshold: float = 0.85
    max_scan_words: int = 10
    decay_rate: float = 0.95

    @property
    def name(self) -> str:
        return "mute_filter"

    def process(self, message: dict) -> PipelineResult:
        """Process message, detecting mute/listen triggers.

        Args:
            message: OpenVIP message dict with 'text' field.

        Returns:
            PipelineResult: PASS, AUGMENT with x_mute, or CONSUME (discard).
        """
        text = message.get("text", "")
        if not text:
            # When muted, discard even empty messages
            if self.is_muted():
                return PipelineResult.consumed()
            return PipelineResult.passed(message)

        tokens = _tokenize(text)
        if not tokens:
            if self.is_muted():
                return PipelineResult.consumed()
            return PipelineResult.passed(message)

        muted = self.is_muted()

        # Check listen triggers first (higher priority when muted)
        if muted:
            listen_match = self._find_match(
                tokens, self.listen_triggers, message,
            )
            if listen_match and listen_match.confidence >= self.confidence_threshold:
                matched_tokens = tokens[listen_match.start_idx : listen_match.end_idx + 1]
                logger.info(
                    "listen_trigger",
                    extra={
                        "pattern": listen_match.pattern,
                        "matched_tokens": matched_tokens,
                        "confidence": listen_match.confidence,
                    },
                )
                new_message = fork_message(message, {
                    "text": "",
                    "x_mute": {
                        "action": "unmute",
                        "trigger": " ".join(matched_tokens),
                        "confidence": round(listen_match.confidence, 3),
                        "source": "dictare/mute-filter",
                    },
                })
                return PipelineResult.consumed([new_message])

            # Muted and no listen trigger: discard silently
            logger.debug("muted_discard: %r", text[:80])
            return PipelineResult.consumed()

        # Not muted: check mute triggers
        mute_match = self._find_match(
            tokens, self.mute_triggers, message,
        )
        if mute_match and mute_match.confidence >= self.confidence_threshold:
            matched_tokens = tokens[mute_match.start_idx : mute_match.end_idx + 1]
            logger.info(
                "mute_trigger",
                extra={
                    "pattern": mute_match.pattern,
                    "matched_tokens": matched_tokens,
                    "confidence": mute_match.confidence,
                },
            )
            new_message = fork_message(message, {
                "text": "",
                "x_mute": {
                    "action": "mute",
                    "trigger": " ".join(matched_tokens),
                    "confidence": round(mute_match.confidence, 3),
                    "source": "dictare/mute-filter",
                },
            })
            return PipelineResult.consumed([new_message])

        # Not muted and no trigger: pass through
        return PipelineResult.passed(message)

    def _find_match(
        self,
        tokens: list[str],
        triggers: dict[str, list[list[str]]],
        message: dict,
    ):
        """Find best trigger match for the given trigger set."""
        active = get_triggers_for_message(triggers, message)
        if not active:
            return None
        return find_best_match(
            tokens, active, self.max_scan_words, self.decay_rate,
        )
