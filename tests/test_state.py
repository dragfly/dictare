"""Tests for engine session state persistence."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dictare.utils.state import SESSION_TIMEOUT_S, clear_state, load_state, save_state

@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """Redirect state file to a temp directory."""
    with patch("dictare.utils.state.get_dictare_dir", return_value=tmp_path):
        yield tmp_path

class TestSaveLoad:
    """save_state / load_state round-trip."""

    def test_save_and_load_defaults(self, state_dir: Path) -> None:
        save_state()
        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] is None
        assert loaded["output_mode"] == "keyboard"
        assert loaded["listening"] is False

    def test_save_and_load_custom(self, state_dir: Path) -> None:
        save_state(active_agent="claude", output_mode="agents", listening=True)
        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] == "claude"
        assert loaded["output_mode"] == "agents"
        assert loaded["listening"] is True

    def test_load_missing_file_returns_none(self, state_dir: Path) -> None:
        assert load_state() is None

    def test_load_corrupt_json_returns_none(self, state_dir: Path) -> None:
        (state_dir / "session-state.json").write_text("not json{{{")
        assert load_state() is None

    def test_load_partial_data_fills_defaults(self, state_dir: Path) -> None:
        data = {"active_agent": "aider", "last_active": time.time()}
        (state_dir / "session-state.json").write_text(json.dumps(data))
        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] == "aider"
        assert loaded["output_mode"] is None
        assert loaded["listening"] is False

    def test_clear_state_removes_file(self, state_dir: Path) -> None:
        save_state(active_agent="claude")
        assert (state_dir / "session-state.json").exists()
        clear_state()
        assert not (state_dir / "session-state.json").exists()

    def test_clear_missing_file_no_error(self, state_dir: Path) -> None:
        clear_state()  # Should not raise

class TestSessionExpiry:
    """Session timeout behavior."""

    def test_fresh_session_returns_state(self, state_dir: Path) -> None:
        save_state(output_mode="agents", active_agent="claude")
        loaded = load_state()
        assert loaded is not None
        assert loaded["output_mode"] == "agents"

    def test_expired_session_returns_none(self, state_dir: Path) -> None:
        # Write state with a timestamp from 2 hours ago
        data = {
            "active_agent": "claude",
            "output_mode": "agents",
            "listening": True,
            "last_active": time.time() - SESSION_TIMEOUT_S - 1,
        }
        (state_dir / "session-state.json").write_text(json.dumps(data))
        assert load_state() is None

    def test_session_just_within_timeout(self, state_dir: Path) -> None:
        data = {
            "active_agent": "claude",
            "output_mode": "agents",
            "listening": True,
            "last_active": time.time() - SESSION_TIMEOUT_S + 60,  # 1 min to spare
        }
        (state_dir / "session-state.json").write_text(json.dumps(data))
        loaded = load_state()
        assert loaded is not None
        assert loaded["output_mode"] == "agents"

    def test_missing_timestamp_treated_as_expired(self, state_dir: Path) -> None:
        data = {"active_agent": "claude", "output_mode": "agents"}
        (state_dir / "session-state.json").write_text(json.dumps(data))
        assert load_state() is None

class TestEnginePersistState:
    """Engine._persist_state / _restore_state integration."""

    def _make_engine(self):
        """Create a minimal engine for state tests."""
        from dictare.config import TTSConfig
        from dictare.core.engine import DictareEngine

        config = MagicMock()
        config.verbose = False
        config.stt = MagicMock()
        config.stt.hw_accel = False
        config.stt.model = "tiny"
        config.stt.advanced.device = "cpu"
        config.stt.advanced.compute_type = "int8"
        config.stt.language = "en"
        config.stt.advanced.hotwords = ""
        config.stt.advanced.beam_size = 5
        config.stt.advanced.max_repetitions = 3
        config.stt.translate = False
        config.audio = MagicMock()
        config.audio.silence_ms = 1200
        config.audio.advanced.sample_rate = 16000
        config.audio.headphones_mode = True
        config.output = MagicMock()
        config.output.mode = "keyboard"
        config.output.auto_enter = True
        config.hotkey = MagicMock()
        config.hotkey.key = "F18"
        config.hotkey.device = None
        config.tts = TTSConfig(engine="espeak", language="en", speed=175, voice="")
        config.pipeline = MagicMock()
        config.pipeline.enabled = False

        return DictareEngine(
            config=config,
            agent_mode=True,
            hotkey_enabled=False,
        )

    def test_persist_saves_current_state(self, state_dir: Path) -> None:
        engine = self._make_engine()
        engine._running = True
        engine.agent_mode = True
        engine._current_agent_id = "claude"
        engine._persist_state()

        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] == "claude"
        assert loaded["output_mode"] == "agents"

    def test_persist_keyboard_mode(self, state_dir: Path) -> None:
        engine = self._make_engine()
        engine._running = True
        engine.agent_mode = False
        engine._current_agent_id = "__keyboard__"
        engine._persist_state()

        loaded = load_state()
        assert loaded is not None
        assert loaded["output_mode"] == "keyboard"

    def test_persist_skipped_during_shutdown(self, state_dir: Path) -> None:
        engine = self._make_engine()
        engine._running = True
        engine.agent_mode = True
        engine._current_agent_id = "voice"
        engine._persist_state()

        # Simulate shutdown: _running = False, agent cleared
        engine._running = False
        engine._current_agent_id = None
        engine._persist_state()

        # State file should still have "voice" (not overwritten)
        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] == "voice"

    def test_restore_from_fresh_session(self, state_dir: Path) -> None:
        save_state(output_mode="agents", active_agent="claude")
        engine = self._make_engine()
        engine.agent_mode = False
        engine._restore_state()
        assert engine.agent_mode is True

    def test_restore_sets_preferred_agent(self, state_dir: Path) -> None:
        save_state(output_mode="agents", active_agent="claude")
        engine = self._make_engine()
        engine._restore_state()
        assert engine._last_sse_agent_id == "claude"

    def test_restore_ignores_keyboard_agent(self, state_dir: Path) -> None:
        save_state(output_mode="keyboard", active_agent="__keyboard__")
        engine = self._make_engine()
        engine._restore_state()
        assert engine._last_sse_agent_id is None

    def test_restore_expired_session_keeps_config_defaults(self, state_dir: Path) -> None:
        """Expired session → config.toml defaults are kept, not overridden."""
        data = {
            "active_agent": "claude",
            "output_mode": "agents",
            "listening": True,
            "last_active": time.time() - SESSION_TIMEOUT_S - 1,
        }
        (state_dir / "session-state.json").write_text(json.dumps(data))

        engine = self._make_engine()
        engine.agent_mode = False  # config.toml says keyboard
        engine._restore_state()
        # Should NOT switch to agents — session expired
        assert engine.agent_mode is False
        assert engine._last_sse_agent_id is None

    def test_restore_no_file_keeps_config_defaults(self, state_dir: Path) -> None:
        """No session file → config.toml defaults are kept."""
        engine = self._make_engine()
        engine.agent_mode = False
        engine._restore_state()
        assert engine.agent_mode is False

class TestRegisterAgentPreferred:
    """register_agent activates saved preferred agent."""

    def _make_engine(self):
        from dictare.config import TTSConfig
        from dictare.core.engine import DictareEngine

        config = MagicMock()
        config.verbose = False
        config.stt = MagicMock()
        config.stt.hw_accel = False
        config.stt.model = "tiny"
        config.stt.advanced.device = "cpu"
        config.stt.advanced.compute_type = "int8"
        config.stt.language = "en"
        config.stt.advanced.hotwords = ""
        config.stt.advanced.beam_size = 5
        config.stt.advanced.max_repetitions = 3
        config.stt.translate = False
        config.audio = MagicMock()
        config.audio.silence_ms = 1200
        config.audio.advanced.sample_rate = 16000
        config.audio.headphones_mode = True
        config.output = MagicMock()
        config.output.mode = "agents"
        config.output.auto_enter = True
        config.hotkey = MagicMock()
        config.hotkey.key = "F18"
        config.hotkey.device = None
        config.tts = TTSConfig(engine="espeak", language="en", speed=175, voice="")
        config.pipeline = MagicMock()
        config.pipeline.enabled = False

        return DictareEngine(
            config=config,
            agent_mode=True,
            hotkey_enabled=False,
        )

    def test_preferred_agent_activated_on_register(self) -> None:
        engine = self._make_engine()
        engine._last_sse_agent_id = "aider"

        # Register a different agent first
        agent1 = MagicMock()
        agent1.id = "claude"
        engine.register_agent(agent1)
        assert engine._current_agent_id == "claude"

        # Register the preferred agent — should become current
        agent2 = MagicMock()
        agent2.id = "aider"
        engine.register_agent(agent2)
        assert engine._current_agent_id == "aider"

    def test_first_agent_becomes_current_without_preference(self) -> None:
        engine = self._make_engine()
        engine._last_sse_agent_id = None

        agent = MagicMock()
        agent.id = "claude"
        engine.register_agent(agent)
        assert engine._current_agent_id == "claude"

class TestGracePeriod:
    """Preferred agent grace period after restore."""

    def _make_engine(self):
        from dictare.config import TTSConfig
        from dictare.core.engine import DictareEngine

        config = MagicMock()
        config.verbose = False
        config.stt = MagicMock()
        config.stt.hw_accel = False
        config.stt.model = "tiny"
        config.stt.advanced.device = "cpu"
        config.stt.advanced.compute_type = "int8"
        config.stt.language = "en"
        config.stt.advanced.hotwords = ""
        config.stt.advanced.beam_size = 5
        config.stt.advanced.max_repetitions = 3
        config.stt.translate = False
        config.audio = MagicMock()
        config.audio.silence_ms = 1200
        config.audio.advanced.sample_rate = 16000
        config.audio.headphones_mode = True
        config.output = MagicMock()
        config.output.mode = "agents"
        config.output.auto_enter = True
        config.hotkey = MagicMock()
        config.hotkey.key = "F18"
        config.hotkey.device = None
        config.tts = TTSConfig(engine="espeak", language="en", speed=175, voice="")
        config.pipeline = MagicMock()
        config.pipeline.enabled = False

        return DictareEngine(
            config=config,
            agent_mode=True,
            hotkey_enabled=False,
        )

    def test_restore_sets_grace_period(self, state_dir: Path) -> None:
        """Fresh session with preferred agent sets a grace deadline."""
        save_state(output_mode="agents", active_agent="claude")
        engine = self._make_engine()
        engine._restore_state()
        assert engine._preferred_agent_deadline is not None

    def test_restore_no_session_no_grace_period(self, state_dir: Path) -> None:
        """No session file → no grace period."""
        engine = self._make_engine()
        engine._restore_state()
        assert engine._preferred_agent_deadline is None

    def test_grace_period_expired_activates_first_agent(self, state_dir: Path) -> None:
        """After grace expires, first available agent becomes active."""
        save_state(output_mode="agents", active_agent="claude")
        engine = self._make_engine()
        engine._restore_state()

        # Register a different agent (not the preferred one)
        agent = MagicMock()
        agent.id = "aider"
        engine.register_agent(agent)

        # Force deadline to past
        engine._preferred_agent_deadline = 0.0
        engine._check_grace_period()

        assert engine._current_agent_id == "aider"
        assert engine._preferred_agent_deadline is None

    def test_grace_period_not_expired_waits(self, state_dir: Path) -> None:
        """Before grace expires, check does nothing."""
        import time as _time

        save_state(output_mode="agents", active_agent="claude")
        engine = self._make_engine()
        engine._restore_state()

        # Deadline is in the future — check should be a no-op
        assert engine._preferred_agent_deadline is not None
        assert engine._preferred_agent_deadline > _time.monotonic()
        engine._check_grace_period()  # Should not crash or change anything

    def test_preferred_agent_arrives_within_grace(self, state_dir: Path) -> None:
        """Preferred agent reconnects within grace period → activated."""
        save_state(output_mode="agents", active_agent="claude")
        engine = self._make_engine()
        engine._restore_state()

        # The preferred agent reconnects
        agent = MagicMock()
        agent.id = "claude"
        engine.register_agent(agent)
        assert engine._current_agent_id == "claude"
