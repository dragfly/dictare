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

# ---------------------------------------------------------------------------
# state.py — save / load round-trip
# ---------------------------------------------------------------------------

class TestSaveLoad:
    """save_state / load_state round-trip."""

    def test_save_and_load_defaults(self, state_dir: Path) -> None:
        save_state()
        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] is None
        assert loaded["listening"] is False

    def test_save_and_load_custom(self, state_dir: Path) -> None:
        save_state(active_agent="claude", listening=True)
        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] == "claude"
        assert loaded["listening"] is True

    def test_no_output_mode_in_file(self, state_dir: Path) -> None:
        """output_mode is never persisted."""
        save_state(active_agent="claude", listening=True)
        raw = json.loads((state_dir / "session-state.json").read_text())
        assert "output_mode" not in raw

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
        assert loaded["listening"] is False

    def test_clear_state_removes_file(self, state_dir: Path) -> None:
        save_state(active_agent="claude")
        assert (state_dir / "session-state.json").exists()
        clear_state()
        assert not (state_dir / "session-state.json").exists()

    def test_clear_missing_file_no_error(self, state_dir: Path) -> None:
        clear_state()  # Should not raise

# ---------------------------------------------------------------------------
# Session timeout
# ---------------------------------------------------------------------------

class TestSessionExpiry:
    """Session timeout behavior."""

    def test_fresh_session_returns_state(self, state_dir: Path) -> None:
        save_state(active_agent="claude")
        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] == "claude"

    def test_expired_session_returns_none(self, state_dir: Path) -> None:
        data = {
            "active_agent": "claude",
            "listening": True,
            "last_active": time.time() - SESSION_TIMEOUT_S - 1,
        }
        (state_dir / "session-state.json").write_text(json.dumps(data))
        assert load_state() is None

    def test_session_just_within_timeout(self, state_dir: Path) -> None:
        data = {
            "active_agent": "claude",
            "listening": True,
            "last_active": time.time() - SESSION_TIMEOUT_S + 60,
        }
        (state_dir / "session-state.json").write_text(json.dumps(data))
        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] == "claude"

    def test_missing_timestamp_treated_as_expired(self, state_dir: Path) -> None:
        data = {"active_agent": "claude"}
        (state_dir / "session-state.json").write_text(json.dumps(data))
        assert load_state() is None

# ---------------------------------------------------------------------------
# Engine integration — _save_state / _restore_state
# ---------------------------------------------------------------------------

def _make_engine(output_mode: str = "agents"):
    """Create a minimal engine for state tests."""
    from dictare.config import TTSConfig
    from dictare.core.engine import DictareEngine

    config = MagicMock()
    config.log_level = "info"
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
    config.output.mode = output_mode
    config.output.auto_submit = True
    config.hotkey = MagicMock()
    config.hotkey.key = "F18"
    config.hotkey.device = None
    config.tts = TTSConfig(engine="espeak", language="en", speed=175, voice="")
    config.pipeline = MagicMock()
    config.pipeline.enabled = False

    return DictareEngine(config=config, hotkey_enabled=False)

class TestAgentModeProperty:
    """agent_mode is derived from _current_agent_id."""

    def test_none_is_agent_mode(self) -> None:
        engine = _make_engine("agents")
        assert engine._agent_mgr._current_agent_id is None
        assert engine.agent_mode is True

    def test_keyboard_is_keyboard_mode(self) -> None:
        engine = _make_engine("keyboard")
        from dictare.core.engine import DictareEngine

        assert engine._agent_mgr._current_agent_id == DictareEngine.KEYBOARD_AGENT_ID
        assert engine.agent_mode is False

    def test_real_agent_is_agent_mode(self) -> None:
        engine = _make_engine("agents")
        engine._agent_mgr._current_agent_id = "voice"
        assert engine.agent_mode is True

    def test_mode_follows_current_agent(self) -> None:
        """Changing _current_agent_id immediately changes agent_mode."""
        from dictare.core.engine import DictareEngine

        engine = _make_engine("agents")
        engine._agent_mgr._current_agent_id = DictareEngine.KEYBOARD_AGENT_ID
        assert engine.agent_mode is False
        engine._agent_mgr._current_agent_id = "voice"
        assert engine.agent_mode is True

class TestEngineSaveState:
    """Engine._save_state round-trip."""

    def test_save_agent_and_listening(self, state_dir: Path) -> None:
        engine = _make_engine()
        engine._running = True
        engine._agent_mgr._current_agent_id = "claude"
        engine._save_state()

        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] == "claude"

    def test_save_skipped_during_shutdown(self, state_dir: Path) -> None:
        engine = _make_engine()
        engine._running = True
        engine._agent_mgr._current_agent_id = "voice"
        engine._save_state()

        engine._running = False
        engine._agent_mgr._current_agent_id = None
        engine._save_state()  # Should be a no-op

        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] == "voice"

    def test_save_before_shutdown_bypasses_running_guard(self, state_dir: Path) -> None:
        engine = _make_engine()
        engine._running = True
        engine._agent_mgr._current_agent_id = "voice"
        engine.save_session_before_shutdown()

        loaded = load_state()
        assert loaded is not None
        assert loaded["active_agent"] == "voice"

class TestEngineRestoreState:
    """Engine._restore_state overrides config from session."""

    def test_restore_sets_preferred_agent(self, state_dir: Path) -> None:
        save_state(active_agent="claude")
        engine = _make_engine()
        engine._restore_state(start_listening=False)
        assert engine._agent_mgr._last_sse_agent_id == "claude"
        assert engine._agent_mgr._preferred_agent_deadline is not None

    def test_restore_keyboard_agent(self, state_dir: Path) -> None:
        from dictare.core.engine import DictareEngine

        save_state(active_agent=DictareEngine.KEYBOARD_AGENT_ID)
        engine = _make_engine()
        engine._restore_state(start_listening=False)
        assert engine._agent_mgr._current_agent_id == DictareEngine.KEYBOARD_AGENT_ID
        assert engine.agent_mode is False
        assert engine._agent_mgr._last_sse_agent_id is None

    def test_restore_listening(self, state_dir: Path) -> None:
        save_state(active_agent="claude", listening=True)
        engine = _make_engine()
        result = engine._restore_state(start_listening=False)
        assert result is True  # listening restored

    def test_restore_not_listening(self, state_dir: Path) -> None:
        save_state(active_agent="claude", listening=False)
        engine = _make_engine()
        result = engine._restore_state(start_listening=False)
        assert result is False

    def test_expired_session_uses_config(self, state_dir: Path) -> None:
        data = {
            "active_agent": "claude",
            "listening": True,
            "last_active": time.time() - SESSION_TIMEOUT_S - 1,
        }
        (state_dir / "session-state.json").write_text(json.dumps(data))

        engine = _make_engine("keyboard")
        result = engine._restore_state(start_listening=False)
        assert result is False  # config default, not restored
        assert engine.agent_mode is False  # config says keyboard

    def test_no_file_uses_config(self, state_dir: Path) -> None:
        engine = _make_engine("keyboard")
        result = engine._restore_state(start_listening=False)
        assert result is False
        assert engine.agent_mode is False

# ---------------------------------------------------------------------------
# Grace period
# ---------------------------------------------------------------------------

class TestGracePeriod:
    """Preferred agent grace period after restore."""

    def test_restore_sets_grace_period(self, state_dir: Path) -> None:
        save_state(active_agent="claude")
        engine = _make_engine()
        engine._restore_state(start_listening=False)
        assert engine._agent_mgr._preferred_agent_deadline is not None

    def test_no_session_no_grace_period(self, state_dir: Path) -> None:
        engine = _make_engine()
        engine._restore_state(start_listening=False)
        assert engine._agent_mgr._preferred_agent_deadline is None

    def test_grace_expired_activates_first_agent(self, state_dir: Path) -> None:
        save_state(active_agent="claude")
        engine = _make_engine()
        engine._restore_state(start_listening=False)

        agent = MagicMock()
        agent.id = "aider"
        engine.register_agent(agent)

        engine._agent_mgr._preferred_agent_deadline = 0.0
        engine._check_grace_period()

        assert engine._agent_mgr._current_agent_id == "aider"
        assert engine._agent_mgr._preferred_agent_deadline is None

    def test_grace_not_expired_waits(self, state_dir: Path) -> None:
        import time as _time

        save_state(active_agent="claude")
        engine = _make_engine()
        engine._restore_state(start_listening=False)

        assert engine._agent_mgr._preferred_agent_deadline is not None
        assert engine._agent_mgr._preferred_agent_deadline > _time.monotonic()
        engine._check_grace_period()

    def test_preferred_agent_arrives_within_grace(self, state_dir: Path) -> None:
        save_state(active_agent="claude")
        engine = _make_engine()
        engine._restore_state(start_listening=False)

        agent = MagicMock()
        agent.id = "claude"
        engine.register_agent(agent)
        assert engine._agent_mgr._current_agent_id == "claude"

# ---------------------------------------------------------------------------
# register_agent with preferred agent
# ---------------------------------------------------------------------------

class TestRegisterAgentPreferred:
    """register_agent activates saved preferred agent."""

    def test_preferred_agent_activated_on_register(self) -> None:
        engine = _make_engine()
        engine._agent_mgr._last_sse_agent_id = "aider"

        agent1 = MagicMock()
        agent1.id = "claude"
        engine.register_agent(agent1)
        assert engine._agent_mgr._current_agent_id == "claude"

        agent2 = MagicMock()
        agent2.id = "aider"
        engine.register_agent(agent2)
        assert engine._agent_mgr._current_agent_id == "aider"

    def test_first_agent_becomes_current_without_preference(self) -> None:
        engine = _make_engine()
        engine._agent_mgr._last_sse_agent_id = None

        agent = MagicMock()
        agent.id = "claude"
        engine.register_agent(agent)
        assert engine._agent_mgr._current_agent_id == "claude"
