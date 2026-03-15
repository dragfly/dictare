"""Tests for AudioFeedbackPolicy."""

from __future__ import annotations

import threading

from dictare.audio.feedback_policy import AudioFeedbackPolicy
from dictare.config import AudioConfig, SoundConfig


def _audio_config(**overrides: SoundConfig) -> AudioConfig:
    """Build AudioConfig with custom per-event SoundConfig."""
    sounds = {
        "start": SoundConfig(),
        "stop": SoundConfig(),
        "transcribed": SoundConfig(volume=0.15, focus_gated=True),
        "sent": SoundConfig(volume=0.25, focus_gated=False),
    }
    sounds.update(overrides)
    return AudioConfig(sounds=sounds)

class TestShouldPlay:
    """Tests for should_play() logic."""

    def test_focus_gated_no_info_returns_true(self) -> None:
        """No focus info → safe default: play."""
        policy = AudioFeedbackPolicy()
        cfg = _audio_config()
        assert policy.should_play("transcribed", "claude", cfg) is True

    def test_focus_gated_agent_focused_returns_false(self) -> None:
        """Agent focused → skip focus-gated sounds."""
        policy = AudioFeedbackPolicy()
        policy.set_focus("claude", True)
        cfg = _audio_config()
        assert policy.should_play("transcribed", "claude", cfg) is False

    def test_focus_gated_agent_not_focused_returns_true(self) -> None:
        """Agent not focused → play focus-gated sounds."""
        policy = AudioFeedbackPolicy()
        policy.set_focus("claude", False)
        cfg = _audio_config()
        assert policy.should_play("transcribed", "claude", cfg) is True

    def test_non_gated_always_plays(self) -> None:
        """Non-focus-gated events always play regardless of focus."""
        policy = AudioFeedbackPolicy()
        policy.set_focus("claude", True)
        cfg = _audio_config()
        assert policy.should_play("start", "claude", cfg) is True
        assert policy.should_play("sent", "claude", cfg) is True

    def test_no_agent_always_plays(self) -> None:
        """No current agent → always play."""
        policy = AudioFeedbackPolicy()
        cfg = _audio_config()
        assert policy.should_play("transcribed", None, cfg) is True

    def test_unknown_event_always_plays(self) -> None:
        """Unknown event (not in config) → always play."""
        policy = AudioFeedbackPolicy()
        policy.set_focus("claude", True)
        cfg = _audio_config()
        assert policy.should_play("unknown_event", "claude", cfg) is True

    def test_remove_agent_cleans_up(self) -> None:
        """remove_agent() removes focus state → subsequent should_play defaults to True."""
        policy = AudioFeedbackPolicy()
        policy.set_focus("claude", True)
        cfg = _audio_config()
        assert policy.should_play("transcribed", "claude", cfg) is False

        policy.remove_agent("claude")
        assert policy.should_play("transcribed", "claude", cfg) is True

    def test_remove_agent_nonexistent_is_noop(self) -> None:
        """Removing a non-existent agent does not raise."""
        policy = AudioFeedbackPolicy()
        policy.remove_agent("nonexistent")  # should not raise

    def test_sent_focus_gated_when_configured(self) -> None:
        """User can override sent to be focus-gated."""
        policy = AudioFeedbackPolicy()
        policy.set_focus("claude", True)
        cfg = _audio_config(sent=SoundConfig(volume=0.25, focus_gated=True))
        assert policy.should_play("sent", "claude", cfg) is False

    def test_multiple_agents_independent(self) -> None:
        """Focus state is per-agent."""
        policy = AudioFeedbackPolicy()
        policy.set_focus("claude", True)
        policy.set_focus("cursor", False)
        cfg = _audio_config()
        assert policy.should_play("transcribed", "claude", cfg) is False
        assert policy.should_play("transcribed", "cursor", cfg) is True

class TestThreadSafety:
    """Concurrent access must not crash."""

    def test_concurrent_set_focus_and_should_play(self) -> None:
        policy = AudioFeedbackPolicy()
        cfg = _audio_config()
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for i in range(200):
                    policy.set_focus(f"agent-{i % 5}", i % 2 == 0)
            except Exception as e:
                errors.append(e)

        def reader() -> None:
            try:
                for i in range(200):
                    policy.should_play("transcribed", f"agent-{i % 5}", cfg)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors
