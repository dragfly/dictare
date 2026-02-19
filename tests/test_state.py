"""Tests for engine state persistence."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voxtype.utils.state import clear_state, load_state, save_state


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """Redirect state file to a temp directory."""
    with patch("voxtype.utils.state.get_voxtype_dir", return_value=tmp_path):
        yield tmp_path


class TestSaveLoad:
    """save_state / load_state round-trip."""

    def test_save_and_load_defaults(self, state_dir: Path) -> None:
        save_state()
        loaded = load_state()
        assert loaded["active_agent"] is None
        assert loaded["output_mode"] == "keyboard"
        assert loaded["listening"] is False

    def test_save_and_load_custom(self, state_dir: Path) -> None:
        save_state(active_agent="claude", output_mode="agents", listening=True)
        loaded = load_state()
        assert loaded["active_agent"] == "claude"
        assert loaded["output_mode"] == "agents"
        assert loaded["listening"] is True

    def test_load_missing_file_returns_defaults(self, state_dir: Path) -> None:
        loaded = load_state()
        assert loaded["active_agent"] is None
        assert loaded["output_mode"] == "keyboard"
        assert loaded["listening"] is False

    def test_load_corrupt_json_returns_defaults(self, state_dir: Path) -> None:
        (state_dir / "state.json").write_text("not json{{{")
        loaded = load_state()
        assert loaded["output_mode"] == "keyboard"

    def test_load_partial_data_fills_defaults(self, state_dir: Path) -> None:
        (state_dir / "state.json").write_text(json.dumps({"active_agent": "aider"}))
        loaded = load_state()
        assert loaded["active_agent"] == "aider"
        assert loaded["output_mode"] == "keyboard"
        assert loaded["listening"] is False

    def test_clear_state_removes_file(self, state_dir: Path) -> None:
        save_state(active_agent="claude")
        assert (state_dir / "state.json").exists()
        clear_state()
        assert not (state_dir / "state.json").exists()

    def test_clear_missing_file_no_error(self, state_dir: Path) -> None:
        clear_state()  # Should not raise


class TestEnginePersistState:
    """Engine._persist_state / _restore_state integration."""

    def _make_engine(self):
        """Create a minimal engine for state tests."""
        from voxtype.config import TTSConfig
        from voxtype.core.engine import VoxtypeEngine

        config = MagicMock()
        config.verbose = False
        config.stt = MagicMock()
        config.stt.hw_accel = False
        config.stt.model = "tiny"
        config.stt.device = "cpu"
        config.stt.compute_type = "int8"
        config.stt.language = "en"
        config.stt.hotwords = None
        config.stt.beam_size = 5
        config.stt.max_repetitions = 3
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

        return VoxtypeEngine(
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
        assert loaded["active_agent"] == "claude"
        assert loaded["output_mode"] == "agents"

    def test_persist_keyboard_mode(self, state_dir: Path) -> None:
        engine = self._make_engine()
        engine._running = True
        engine.agent_mode = False
        engine._current_agent_id = "__keyboard__"
        engine._persist_state()

        loaded = load_state()
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
        assert loaded["active_agent"] == "voice"

    def test_restore_sets_agent_mode(self, state_dir: Path) -> None:
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


class TestRegisterAgentPreferred:
    """register_agent activates saved preferred agent."""

    def _make_engine(self):
        from voxtype.config import TTSConfig
        from voxtype.core.engine import VoxtypeEngine

        config = MagicMock()
        config.verbose = False
        config.stt = MagicMock()
        config.stt.hw_accel = False
        config.stt.model = "tiny"
        config.stt.device = "cpu"
        config.stt.compute_type = "int8"
        config.stt.language = "en"
        config.stt.hotwords = None
        config.stt.beam_size = 5
        config.stt.max_repetitions = 3
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

        return VoxtypeEngine(
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
