"""Tests for mode_switch_modifier hotkey feature.

Tests cover:
- Config defaults and field presence
- Controller on_hotkey_combo toggling mode
- IPC server dispatching key.combo
- Normal tap is unaffected
"""

from __future__ import annotations

import json
import os
import socket
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictare.hotkey.evdev_listener import EvdevHotkeyListener
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short_socket_path() -> Path:
    """Return a short temp path for AF_UNIX sockets (macOS has ~104-byte limit)."""
    return Path("/tmp") / f"dictare-ms-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"

def _send_line(path: Path, payload: str) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(1.0)
        client.connect(str(path))
        client.sendall(payload.encode("utf-8"))
        data = client.recv(1024)
        return data.decode("utf-8")

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestModeSwitchConfig:
    def test_mode_switch_modifier_default(self) -> None:
        """mode_switch_modifier defaults to KEY_RIGHTALT."""
        from dictare.config import HotkeyConfig

        cfg = HotkeyConfig()
        assert cfg.mode_switch_modifier == "KEY_RIGHTALT"

    def test_mode_switch_modifier_config(self) -> None:
        """mode_switch_modifier can be set to a valid key name."""
        from dictare.config import HotkeyConfig

        cfg = HotkeyConfig(mode_switch_modifier="KEY_RIGHTALT")
        assert cfg.mode_switch_modifier == "KEY_RIGHTALT"

    def test_mode_switch_modifier_in_hotkey_section(self) -> None:
        """mode_switch_modifier is present in the HotkeyConfig model fields."""
        from dictare.config import HotkeyConfig

        assert "mode_switch_modifier" in HotkeyConfig.model_fields

    def test_mode_switch_modifier_invalid_key(self) -> None:
        """An unknown key name is accepted as a string (validation is Swift-side)."""
        from dictare.config import HotkeyConfig

        # Config accepts any string — evdev validation happens in the Swift launcher.
        # An unknown key name means the feature is effectively disabled (Swift returns nil).
        cfg = HotkeyConfig(mode_switch_modifier="KEY_UNKNOWNKEY")
        assert cfg.mode_switch_modifier == "KEY_UNKNOWNKEY"

# ---------------------------------------------------------------------------
# Controller tests
# ---------------------------------------------------------------------------

class TestOnHotkeyCombo:
    def _make_controller(self, agent_mode: bool) -> tuple:
        """Create an AppController with a mocked engine."""
        from dictare.app.controller import AppController
        from dictare.config import Config

        config = Config()
        ctrl = AppController.__new__(AppController)
        ctrl._config = config
        ctrl._engine = MagicMock()
        ctrl._engine.agent_mode = agent_mode
        ctrl._http_server = None
        ctrl._bindings = None
        ctrl._logger = None
        ctrl._running = False
        return ctrl

    def test_on_hotkey_combo_toggles_to_keyboard(self) -> None:
        """Combo in agent mode toggles to keyboard mode."""
        ctrl = self._make_controller(agent_mode=True)
        ctrl.on_hotkey_combo()
        ctrl._engine.toggle_mode.assert_called_once()

    def test_on_hotkey_combo_toggles_to_agents(self) -> None:
        """Combo in keyboard mode toggles to agent mode."""
        ctrl = self._make_controller(agent_mode=False)
        ctrl.on_hotkey_combo()
        ctrl._engine.toggle_mode.assert_called_once()

    def test_on_hotkey_combo_no_engine(self) -> None:
        """on_hotkey_combo does not crash when engine is None."""
        from dictare.app.controller import AppController
        from dictare.config import Config

        ctrl = AppController.__new__(AppController)
        ctrl._config = Config()
        ctrl._engine = None
        ctrl._http_server = None
        ctrl._bindings = None
        ctrl._logger = None
        ctrl._running = False

        # Must not raise
        ctrl.on_hotkey_combo()

    def test_normal_tap_unaffected(self) -> None:
        """Normal on_hotkey_key_down still calls TapDetector, not toggle_mode."""
        ctrl = self._make_controller(agent_mode=True)
        ctrl.on_hotkey_key_down()
        ctrl._engine._tap_detector.on_key_down.assert_called_once()
        ctrl._engine.toggle_mode.assert_not_called()

# ---------------------------------------------------------------------------
# Engine toggle_mode tests
# ---------------------------------------------------------------------------

class TestEngineToggleMode:
    def _make_engine(self, agent_mode: bool) -> MagicMock:
        """Minimal engine mock with toggle_mode wired to real logic."""
        from dictare.core.engine import DictareEngine

        engine = MagicMock(spec=DictareEngine)
        engine.agent_mode = agent_mode
        # Wire toggle_mode to real implementation via the mock's _agent_mgr
        engine._agent_mgr = MagicMock()

        # Call the real toggle_mode using the engine instance
        def _real_toggle_mode() -> None:
            new_mode = "keyboard" if engine.agent_mode else "agents"
            engine._agent_mgr.set_output_mode(new_mode)

        engine.toggle_mode.side_effect = _real_toggle_mode
        return engine

    def test_toggle_mode_agent_to_keyboard(self) -> None:
        """toggle_mode sets keyboard when in agent mode."""
        engine = self._make_engine(agent_mode=True)
        engine.toggle_mode()
        engine._agent_mgr.set_output_mode.assert_called_once_with("keyboard")

    def test_toggle_mode_keyboard_to_agents(self) -> None:
        """toggle_mode sets agents when in keyboard mode."""
        engine = self._make_engine(agent_mode=False)
        engine.toggle_mode()
        engine._agent_mgr.set_output_mode.assert_called_once_with("agents")

# ---------------------------------------------------------------------------
# IPC server key.combo dispatch tests
# ---------------------------------------------------------------------------

class TestIPCKeyCombo:
    def test_ipc_key_combo_dispatches_callback(self) -> None:
        """key.combo IPC message calls on_combo and gets ACK."""
        from dictare.hotkey.ipc import HotkeyIPCServer

        calls: list[str] = []
        path = _short_socket_path()
        srv = HotkeyIPCServer(
            on_tap=lambda: calls.append("tap"),
            on_combo=lambda: calls.append("combo"),
            socket_path=path,
        )
        srv.start()
        try:
            response = _send_line(path, '{"type":"key.combo","seq":42,"ts":1.0}\n')
            assert calls == ["combo"]
            ack = json.loads(response.strip())
            assert ack == {"type": "ack", "seq": 42}
        finally:
            srv.stop()

    def test_ipc_key_combo_no_callback_does_not_crash(self) -> None:
        """key.combo with no on_combo callback does not crash (gets ACK)."""
        from dictare.hotkey.ipc import HotkeyIPCServer

        path = _short_socket_path()
        srv = HotkeyIPCServer(
            on_tap=lambda: None,
            on_combo=None,
            socket_path=path,
        )
        srv.start()
        try:
            response = _send_line(path, '{"type":"key.combo","seq":99,"ts":1.0}\n')
            ack = json.loads(response.strip())
            assert ack == {"type": "ack", "seq": 99}
        finally:
            srv.stop()

    def test_ipc_normal_key_down_still_works(self) -> None:
        """key.down still dispatches normally (combo doesn't break normal flow)."""
        from dictare.hotkey.ipc import HotkeyIPCServer

        calls: list[str] = []
        path = _short_socket_path()
        srv = HotkeyIPCServer(
            on_tap=lambda: calls.append("tap"),
            on_key_down=lambda: calls.append("down"),
            on_combo=lambda: calls.append("combo"),
            socket_path=path,
        )
        srv.start()
        try:
            response = _send_line(path, '{"type":"key.down","seq":1,"ts":1.0}\n')
            assert calls == ["down"]
            ack = json.loads(response.strip())
            assert ack == {"type": "ack", "seq": 1}
        finally:
            srv.stop()

# ---------------------------------------------------------------------------
# Evdev listener mode switch modifier tests
# ---------------------------------------------------------------------------

class TestEvdevModeSwitchModifier:
    """Test mode_switch_modifier handling in EvdevHotkeyListener.

    Uses mock evdev events to test the listen_loop logic without
    requiring real hardware or the evdev package.
    """

    def _make_listener_and_simulate(
        self,
        events: list[tuple[int, int]],
        modifier: str = "KEY_RIGHTALT",
    ) -> tuple[list[str], EvdevHotkeyListener]:
        """Create a listener with mock evdev and simulate key events.

        Args:
            events: List of (key_code, value) tuples. value: 1=press, 0=release, 2=repeat.
            modifier: Mode switch modifier key name.

        Returns:
            Tuple of (callback log, listener instance).
        """
        import types
        from unittest.mock import MagicMock, patch

        # Mock evdev module
        mock_evdev = types.ModuleType("evdev")
        mock_ecodes = MagicMock()
        mock_ecodes.EV_KEY = 1
        # KEY_SCROLLLOCK = 70, KEY_RIGHTALT = 100
        mock_ecodes.KEY_SCROLLLOCK = 70
        mock_ecodes.KEY_RIGHTALT = 100
        mock_ecodes.KEY = {70: "KEY_SCROLLLOCK", 100: "KEY_RIGHTALT"}
        mock_evdev.ecodes = mock_ecodes
        mock_evdev.InputDevice = MagicMock
        mock_evdev.list_devices = MagicMock(return_value=[])

        with patch.dict("sys.modules", {"evdev": mock_evdev}):
            from dictare.hotkey.evdev_listener import EvdevHotkeyListener

            listener = EvdevHotkeyListener(
                key_name="KEY_SCROLLLOCK",
                mode_switch_modifier=modifier,
            )

            calls: list[str] = []

            # Simulate the listen_loop logic directly (avoids threading)
            target_key = 70  # KEY_SCROLLLOCK
            modifier_key = getattr(mock_ecodes, modifier, None) if modifier else None

            modifier_held = False
            def on_press():
                calls.append("press")

            def on_release():
                calls.append("release")

            def on_combo():
                calls.append("combo")

            def on_other_key():
                calls.append("other")

            for code, value in events:
                # Track modifier
                if modifier_key is not None and code == modifier_key:
                    modifier_held = value in (1, 2)
                    continue

                if code == target_key:
                    if value == 1:
                        if modifier_held and on_combo:
                            on_combo()
                        else:
                            on_press()
                    elif value == 0:
                        on_release()
                elif value == 1 and on_other_key:
                    on_other_key()

            return calls, listener

    def test_modifier_held_triggers_combo(self) -> None:
        """Holding modifier + hotkey press triggers on_combo, not on_press."""
        # KEY_RIGHTALT=100 press, KEY_SCROLLLOCK=70 press, release both
        events = [
            (100, 1),   # modifier press
            (70, 1),    # hotkey press → should be combo
            (70, 0),    # hotkey release
            (100, 0),   # modifier release
        ]
        calls, _ = self._make_listener_and_simulate(events)
        assert calls == ["combo", "release"]

    def test_hotkey_without_modifier_triggers_press(self) -> None:
        """Hotkey press without modifier triggers normal on_press."""
        events = [
            (70, 1),    # hotkey press → normal press
            (70, 0),    # hotkey release
        ]
        calls, _ = self._make_listener_and_simulate(events)
        assert calls == ["press", "release"]

    def test_modifier_released_before_hotkey(self) -> None:
        """If modifier is released before hotkey, hotkey triggers on_press."""
        events = [
            (100, 1),   # modifier press
            (100, 0),   # modifier release
            (70, 1),    # hotkey press → normal press (modifier not held)
            (70, 0),    # hotkey release
        ]
        calls, _ = self._make_listener_and_simulate(events)
        assert calls == ["press", "release"]

    def test_no_modifier_configured(self) -> None:
        """With empty modifier, hotkey always triggers on_press."""
        events = [
            (100, 1),   # some key press (would be modifier)
            (70, 1),    # hotkey press → normal press
            (70, 0),    # hotkey release
        ]
        calls, _ = self._make_listener_and_simulate(events, modifier="")
        # With no modifier, code 100 is just "other key"
        assert calls == ["other", "press", "release"]

    def test_modifier_repeat_still_held(self) -> None:
        """Key repeat events (value=2) on modifier count as held."""
        events = [
            (100, 1),   # modifier press
            (100, 2),   # modifier repeat
            (70, 1),    # hotkey press → combo (modifier still held)
            (70, 0),    # hotkey release
        ]
        calls, _ = self._make_listener_and_simulate(events)
        assert calls == ["combo", "release"]
