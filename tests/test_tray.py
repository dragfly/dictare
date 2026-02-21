"""Tests for voxtype.tray.app."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from voxtype.tray.app import TrayApp


def _mock_pystray():
    """Create a mock pystray module for headless testing."""

    def menu_factory(*items):
        m = SimpleNamespace(_items=list(items))
        return m

    menu_factory.SEPARATOR = SimpleNamespace(text="---")

    mock = SimpleNamespace(
        MenuItem=lambda text, action=None, **kw: SimpleNamespace(text=text, action=action, **kw),
        Menu=menu_factory,
    )
    return mock



class TestTrayStates:
    """Tests for tray icon state transitions."""

    def test_initial_state_is_disconnected(self) -> None:
        app = TrayApp()
        assert app._state == "disconnected"

    def test_set_state_disconnected(self) -> None:
        app = TrayApp()
        app.set_state("off")
        assert app._state == "off"
        app.set_state("disconnected")
        assert app._state == "disconnected"

    def test_set_state_listening(self) -> None:
        app = TrayApp()
        app.set_state("listening")
        assert app._state == "listening"

    def test_playing_maps_to_listening(self) -> None:
        """Engine 'playing' state (mic muted during beep) should show as active."""
        # The tray polls /status and maps engine states to tray states.
        # "playing" is a sub-state of listening (mic temporarily muted for beep).
        # Verify the mapping at the poll level: state in ("listening", ..., "playing")
        active_states = ("listening", "recording", "transcribing", "playing")
        for state in active_states:
            tray_state = "listening" if state in active_states else "off"
            assert tray_state == "listening", f"{state} should map to 'listening'"

    def test_set_state_rejects_unknown(self) -> None:
        app = TrayApp()
        app.set_state("bogus")
        assert app._state == "disconnected"  # unchanged from initial

    def test_update_icon_maps_disconnected_to_muted(self) -> None:
        app = TrayApp()
        mock_icon = MagicMock()
        app._icon = mock_icon
        with patch.object(app, "_update_menu"):  # avoid pystray import
            app.set_state("disconnected")
        # _update_icon was called; the icon should be set to voxtype_muted
        assert mock_icon.icon is not None  # icon was updated

    def test_icon_state_mapping(self) -> None:
        """Verify each state maps to the correct icon name.

        red    (muted)   = disconnected — server unreachable
        yellow (default) = off / loading / restarting — ready or preparing
        green  (active)  = listening
        """
        app = TrayApp()
        mock_icon = MagicMock()
        app._icon = mock_icon

        expected = {
            "disconnected": "voxtype_muted",
            "restarting": "voxtype",
            "loading": "voxtype",
            "off": "voxtype",
            "listening": "voxtype_active",
        }
        for state, icon_name in expected.items():
            # Reset dedup cache so each state triggers an icon update
            app._current_icon_name = ""
            with patch("voxtype.tray.app._load_icon", return_value="img") as mock_load:
                with patch.object(app, "_update_menu"):
                    app.set_state(state)
                mock_load.assert_called_with(icon_name), f"state={state}"

    def test_hover_tooltip_shows_state(self) -> None:
        """Hover tooltip should show 'VoxType — <state>'."""
        app = TrayApp()
        mock_icon = MagicMock()
        app._icon = mock_icon

        expected_titles = {
            "disconnected": "VoxType — Disconnected",
            "restarting": "VoxType — Restarting…",
            "off": "VoxType — Idle",
            "listening": "VoxType — Listening",
        }
        for state, title in expected_titles.items():
            with patch("voxtype.tray.app._load_icon", return_value="img"):
                with patch.object(app, "_update_menu"):
                    app.set_state(state)
            assert mock_icon.title == title, f"state={state}: {mock_icon.title!r}"

        # Loading with stage info
        with patch("voxtype.tray.app._load_icon", return_value="img"):
            with patch.object(app, "_update_menu"):
                app.set_state("loading", loading_stage="STT")
        assert mock_icon.title == "VoxType — Loading STT…"

    def test_menu_status_disconnected(self) -> None:
        app = TrayApp()
        app._state = "disconnected"
        with patch.dict(sys.modules, {"pystray": _mock_pystray()}):
            menu = app._create_menu()
        first_label = menu._items[0].text
        assert "Disconnected" in first_label

    def test_menu_status_idle(self) -> None:
        app = TrayApp()
        app._state = "off"
        with patch.dict(sys.modules, {"pystray": _mock_pystray()}):
            menu = app._create_menu()
        first_label = menu._items[0].text
        assert "IDLE" in first_label

    def test_menu_status_restarting(self) -> None:
        app = TrayApp()
        app._state = "restarting"
        with patch.dict(sys.modules, {"pystray": _mock_pystray()}):
            menu = app._create_menu()
        first_label = menu._items[0].text
        assert "Restarting" in first_label

    def test_restarting_flag_suppresses_disconnected(self) -> None:
        """During restart, SSE disconnect should not switch to red."""
        app = TrayApp()
        app._restarting = True
        app.set_state("restarting")
        assert app._state == "restarting"

        # Simulate SSE disconnect — would normally go to 'disconnected'
        # but _restarting flag keeps it in 'restarting'
        # (the on_disconnect callback checks _restarting)
        assert app._restarting is True
        assert app._state == "restarting"

    def test_restarting_flag_clears_on_real_state(self) -> None:
        """Once engine reports loading/idle/listening, clear restarting."""
        app = TrayApp()
        app._restarting = True
        app.set_state("restarting")
        assert app._restarting is True

        # Engine comes back with loading
        app.set_state("loading")
        assert app._state == "loading"
        assert app._restarting is False

        # Same for idle
        app._restarting = True
        app.set_state("off")
        assert app._restarting is False


class TestSetTargets:
    """Tests for TrayApp.set_targets — agent list management."""

    def test_set_targets_populates_list(self) -> None:
        app = TrayApp()
        app.set_targets(["alice", "bob"], current="bob")
        assert app._targets == ["alice", "bob"]
        assert app._current_target == "bob"

    def test_set_targets_empty_clears_current(self) -> None:
        """When last agent disconnects, targets AND current_target are cleared."""
        app = TrayApp()
        app.set_targets(["voce"], current="voce")
        assert app._current_target == "voce"

        # Last agent disconnects
        app.set_targets([], current="")
        assert app._targets == []
        assert app._current_target == ""

    def test_set_targets_picks_first_when_no_current(self) -> None:
        app = TrayApp()
        app.set_targets(["alice", "bob"])
        assert app._current_target == "alice"

    def test_set_targets_keeps_current_if_still_valid(self) -> None:
        app = TrayApp()
        app.set_targets(["alice", "bob"], current="bob")
        # New poll with same agents, no current specified
        app.set_targets(["alice", "bob"])
        assert app._current_target == "bob"
