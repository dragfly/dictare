"""Tests for shared display state resolution."""

from __future__ import annotations

from dictare.status import resolve_display_state


class TestResolveDisplayState:
    """Test resolve_display_state()."""

    # --- Engine-level (no agent_id) ---

    def test_loading_returns_loading_warn(self) -> None:
        platform = {"state": "off", "loading": {"active": True}}
        assert resolve_display_state(platform) == ("loading", "warn")

    def test_listening_returns_listening_ok(self) -> None:
        platform = {"state": "listening", "loading": {"active": False}}
        assert resolve_display_state(platform) == ("listening", "ok")

    def test_recording_returns_listening_ok(self) -> None:
        platform = {"state": "recording"}
        assert resolve_display_state(platform) == ("listening", "ok")

    def test_off_returns_off_dim(self) -> None:
        platform = {"state": "off"}
        assert resolve_display_state(platform) == ("off", "dim")

    def test_missing_state_defaults_off(self) -> None:
        platform = {}
        assert resolve_display_state(platform) == ("off", "dim")

    def test_loading_overrides_listening(self) -> None:
        """Loading takes priority even if engine state is listening."""
        platform = {"state": "listening", "loading": {"active": True}}
        assert resolve_display_state(platform) == ("loading", "warn")

    # --- Per-agent (with agent_id) ---

    def test_active_listening_agent(self) -> None:
        platform = {
            "state": "listening",
            "output": {"current_agent": "claude"},
        }
        assert resolve_display_state(platform, "claude") == ("listening", "ok")

    def test_active_off_agent(self) -> None:
        platform = {
            "state": "off",
            "output": {"current_agent": "claude"},
        }
        assert resolve_display_state(platform, "claude") == ("off", "dim")

    def test_standby_agent(self) -> None:
        platform = {
            "state": "listening",
            "output": {"current_agent": "cursor"},
        }
        assert resolve_display_state(platform, "claude") == ("standby", "warn")

    def test_loading_overrides_agent_state(self) -> None:
        platform = {
            "state": "listening",
            "output": {"current_agent": "claude"},
            "loading": {"active": True},
        }
        assert resolve_display_state(platform, "claude") == ("loading", "warn")

    def test_agent_with_no_current(self) -> None:
        platform = {
            "state": "listening",
            "output": {"current_agent": None},
        }
        assert resolve_display_state(platform, "claude") == ("standby", "warn")

    def test_standby_agent_mic_off(self) -> None:
        """Standby with mic inactive → dim (gray), not warn (yellow)."""
        platform = {
            "state": "off",
            "output": {"current_agent": "cursor"},
        }
        assert resolve_display_state(platform, "claude") == ("standby", "dim")

    def test_standby_agent_no_current_mic_off(self) -> None:
        platform = {
            "state": "off",
            "output": {"current_agent": None},
        }
        assert resolve_display_state(platform, "claude") == ("standby", "dim")
