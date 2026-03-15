"""Tests for cli/shortcuts.py — shortcut normalization and data helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from dictare.cli.shortcuts import (
    AVAILABLE_COMMANDS,
    _command_key,
    _get_current_shortcuts,
    _normalize_shortcut,
    _save_shortcuts,
)


class TestNormalizeShortcut:
    def test_basic_ctrl(self) -> None:
        assert _normalize_shortcut("ctrl+a") == "Ctrl+A"

    def test_control_alias(self) -> None:
        assert _normalize_shortcut("control+b") == "Ctrl+B"

    def test_alt_alias(self) -> None:
        assert _normalize_shortcut("option+x") == "Alt+X"

    def test_opt_alias(self) -> None:
        assert _normalize_shortcut("opt+y") == "Alt+Y"

    def test_cmd_alias(self) -> None:
        assert _normalize_shortcut("command+z") == "Cmd+Z"

    def test_meta_alias(self) -> None:
        assert _normalize_shortcut("meta+k") == "Cmd+K"

    def test_super_alias(self) -> None:
        assert _normalize_shortcut("super+l") == "Cmd+L"

    def test_win_alias(self) -> None:
        assert _normalize_shortcut("win+m") == "Cmd+M"

    def test_shift(self) -> None:
        assert _normalize_shortcut("shift+f1") == "Shift+F1"

    def test_multi_modifier(self) -> None:
        assert _normalize_shortcut("ctrl+shift+a") == "Ctrl+Shift+A"

    def test_hyphen_separator(self) -> None:
        assert _normalize_shortcut("ctrl-alt-n") == "Ctrl+Alt+N"

    def test_spaces_around_parts(self) -> None:
        assert _normalize_shortcut("ctrl + a") == "Ctrl+A"


class TestCommandKey:
    def test_simple_command(self) -> None:
        cmd = {"command": "toggle-listening"}
        assert _command_key(cmd) == "toggle-listening"

    def test_command_with_args(self) -> None:
        cmd = {"command": "switch-to-project-index", "args": {"index": 3}}
        assert _command_key(cmd) == "switch-to-project-index:{'index': 3}"


class TestGetCurrentShortcuts:
    def test_extracts_shortcuts(self) -> None:
        config = MagicMock()
        config.keyboard.shortcuts = [
            {"command": "toggle-listening", "keys": "Ctrl+L"},
            {"command": "switch-to-project-index", "keys": "Ctrl+1", "args": {"index": 1}},
        ]
        result = _get_current_shortcuts(config)
        assert result["toggle-listening"] == "Ctrl+L"
        assert "switch-to-project-index:{'index': 1}" in result

    def test_empty_shortcuts(self) -> None:
        config = MagicMock()
        config.keyboard.shortcuts = []
        result = _get_current_shortcuts(config)
        assert result == {}


class TestSaveShortcuts:
    def test_saves_to_toml(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        shortcuts = {"toggle-listening": "Ctrl+L"}
        _save_shortcuts(shortcuts, config_path)

        assert config_path.exists()
        content = config_path.read_text()
        assert "toggle-listening" in content
        assert "Ctrl+L" in content

    def test_preserves_existing_sections(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('[stt]\nmodel = "base"\n', encoding="utf-8")

        shortcuts = {"toggle-listening": "Ctrl+L"}
        _save_shortcuts(shortcuts, config_path)

        content = config_path.read_text()
        assert 'model = "base"' in content
        assert "toggle-listening" in content

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        config_path = tmp_path / "deep" / "nested" / "config.toml"
        shortcuts = {"toggle-listening": "Ctrl+L"}
        _save_shortcuts(shortcuts, config_path)
        assert config_path.exists()


class TestAvailableCommands:
    def test_commands_have_required_keys(self) -> None:
        for cmd in AVAILABLE_COMMANDS:
            assert "command" in cmd
            assert "description" in cmd
            assert "display" in cmd
