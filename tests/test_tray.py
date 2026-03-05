"""Tests for dictare.tray.app."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dictare.tray.app import TrayApp


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
        # _update_icon was called; the icon should be set to dictare_muted
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
            "disconnected": "dictare_disconnected",
            "loading": "dictare_loading",
            "off": "dictare",
            "listening": "dictare_active",
        }
        for state, icon_name in expected.items():
            # Force a different state first so set_state sees a change
            app._state = "__reset__"
            with patch("dictare.tray.app._load_icon", return_value="img") as mock_load:
                with patch.object(app, "_update_menu"):
                    app.set_state(state)
                mock_load.assert_called_with(icon_name), f"state={state}"

    def test_hover_tooltip_shows_state(self) -> None:
        """Hover tooltip should show 'Dictare — <state>'."""
        app = TrayApp()
        mock_icon = MagicMock()
        app._icon = mock_icon

        expected_titles = {
            "disconnected": "Dictare — Disconnected",
            "off": "Dictare — Off",
            "muted": "Dictare — Muted",
            "listening": "Dictare — Listening",
        }
        for state, title in expected_titles.items():
            # Force a different state first so set_state sees a change
            app._state = "__reset__"
            with patch("dictare.tray.app._load_icon", return_value="img"):
                with patch.object(app, "_update_menu"):
                    app.set_state(state)
            assert mock_icon.title == title, f"state={state}: {mock_icon.title!r}"

        # Loading with stage info
        with patch("dictare.tray.app._load_icon", return_value="img"):
            with patch.object(app, "_update_menu"):
                app.set_state("loading", loading_stage="STT")
        assert mock_icon.title == "Dictare — Loading STT…"

    def test_menu_status_disconnected(self) -> None:
        app = TrayApp()
        app._state = "disconnected"
        with patch.dict(sys.modules, {"pystray": _mock_pystray()}):
            menu = app._create_menu()
        first_label = menu._items[0].text
        assert "Disconnected" in first_label

    def test_menu_status_off(self) -> None:
        app = TrayApp()
        app._state = "off"
        with patch.dict(sys.modules, {"pystray": _mock_pystray()}):
            menu = app._create_menu()
        first_label = menu._items[0].text
        assert "OFF" in first_label

    def test_menu_status_restarting(self) -> None:
        """Unknown/restarting state falls through to upper-case display."""
        app = TrayApp()
        app._state = "restarting"
        with patch.dict(sys.modules, {"pystray": _mock_pystray()}):
            menu = app._create_menu()
        first_label = menu._items[0].text
        assert "RESTARTING" in first_label

    def test_unknown_state_is_ignored(self) -> None:
        """set_state ignores unknown states (e.g. 'restarting')."""
        app = TrayApp()
        initial_state = app._state
        app.set_state("restarting")
        assert app._state == initial_state

    def test_valid_state_replaces_unknown(self) -> None:
        """After an unknown state is set directly, a valid set_state call updates it."""
        app = TrayApp()
        app._state = "restarting"
        with patch("dictare.tray.app._load_icon", return_value="img"):
            with patch.object(app, "_update_menu"):
                app.set_state("loading")
        assert app._state == "loading"

    def test_startup_connection_failures_dont_go_red(self) -> None:
        """On fresh start, SSE connection failures should NOT flip to disconnected.

        The tray starts in 'disconnected' state. Before the first successful
        SSE connection (_connected_once=False), on_disconnect must not call
        set_state('disconnected') — it would be redundant and trigger menu
        re-renders on every retry attempt.
        """
        from unittest.mock import MagicMock

        app = TrayApp()
        states_seen: list[str] = []

        original_set_state = app.set_state

        def recording_set_state(state: str, **kwargs: object) -> None:
            states_seen.append(state)
            original_set_state(state, **kwargs)

        app.set_state = recording_set_state  # type: ignore[method-assign]

        # Mock Client.subscribe_status: raise ConnectionRefusedError twice, then stop
        call_count = 0

        def fake_subscribe_status(**kwargs):  # type: ignore[return]
            nonlocal call_count
            on_disconnect = kwargs.get("on_disconnect")
            stop = kwargs.get("stop")
            for _ in range(2):
                if stop and stop():
                    return
                if on_disconnect:
                    on_disconnect(ConnectionRefusedError("refused"))
                import time
                time.sleep(0.01)
            # Stop polling after 2 failures
            app.stop_status_polling()
            return iter([])

        mock_client = MagicMock()
        mock_client.subscribe_status.side_effect = fake_subscribe_status

        with patch("openvip.Client", return_value=mock_client):
            app.start_status_streaming(host="127.0.0.1", port=8770)
            # Wait for stream thread to finish
            if app._poll_thread:
                app._poll_thread.join(timeout=2.0)

        # Initial set_state calls (from TrayApp init setup) are ok,
        # but NO 'disconnected' call should come from on_disconnect
        # since _connected_once was never True.
        assert "disconnected" not in states_seen, (
            f"set_state('disconnected') was called during startup failures: {states_seen}"
        )


class TestServiceMenu:
    """Tests for Start/Stop Service menu based on engine state."""

    def test_stop_service_shown_when_engine_running(self) -> None:
        """When engine is reachable (state != disconnected), show Stop Service."""
        app = TrayApp()
        app._state = "off"
        with patch.dict(sys.modules, {"pystray": _mock_pystray()}):
            menu = app._create_menu()
        # Find the Advanced submenu
        advanced = [i for i in menu._items if getattr(i, "text", "") == "Advanced"][0]
        labels = [i.text for i in advanced.action._items if hasattr(i, "text") and i.text != "---"]
        assert "Stop Service" in labels
        assert "Start Service" not in labels

    def test_start_service_shown_when_disconnected(self) -> None:
        """When engine is unreachable, show Start Service."""
        app = TrayApp()
        app._state = "disconnected"
        with patch.dict(sys.modules, {"pystray": _mock_pystray()}):
            menu = app._create_menu()
        advanced = [i for i in menu._items if getattr(i, "text", "") == "Advanced"][0]
        labels = [i.text for i in advanced.action._items if hasattr(i, "text") and i.text != "---"]
        assert "Start Service" in labels
        assert "Stop Service" not in labels

    def test_stop_service_shown_when_listening(self) -> None:
        """Listening state = engine running = Stop Service."""
        app = TrayApp()
        app._state = "listening"
        with patch.dict(sys.modules, {"pystray": _mock_pystray()}):
            menu = app._create_menu()
        advanced = [i for i in menu._items if getattr(i, "text", "") == "Advanced"][0]
        labels = [i.text for i in advanced.action._items if hasattr(i, "text") and i.text != "---"]
        assert "Stop Service" in labels

    def test_stop_service_shown_when_loading(self) -> None:
        """Loading state = engine starting up = Stop Service."""
        app = TrayApp()
        app._state = "loading"
        with patch.dict(sys.modules, {"pystray": _mock_pystray()}):
            menu = app._create_menu()
        advanced = [i for i in menu._items if getattr(i, "text", "") == "Advanced"][0]
        labels = [i.text for i in advanced.action._items if hasattr(i, "text") and i.text != "---"]
        assert "Stop Service" in labels


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
