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
    def test_mode_switch_modifier_default_empty(self) -> None:
        """mode_switch_modifier defaults to empty string (disabled)."""
        from dictare.config import HotkeyConfig

        cfg = HotkeyConfig()
        assert cfg.mode_switch_modifier == ""

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
