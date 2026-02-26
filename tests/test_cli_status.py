"""Tests for `dictare status` CLI command."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dictare.cli import app

runner = CliRunner()

def _mock_status() -> MagicMock:
    """Create a mock openvip Status object."""
    status = MagicMock()
    status.openvip = "1.0"
    status.stt = {"enabled": True, "active": False}
    status.tts = {"enabled": True}
    status.connected_agents = ["claude"]
    status.platform = {
        "name": "Dictare",
        "version": "0.1.0b280",
        "mode": "agents",
        "state": "idle",
        "uptime_seconds": 3600,
        "stt": {"model_name": "parakeet-v3", "device": "cpu", "last_text": ""},
        "tts": {"engine": "piper", "language": "en", "available": True, "error": None},
        "output": {"mode": "agents", "current_agent": "claude", "available_agents": ["claude"]},
        "hotkey": {"key": "F13", "bound": True},
        "permissions": {"accessibility": True, "microphone": True},
        "engines": {
            "tts": [
                {"name": "say", "available": True, "description": "macOS built-in", "platform_ok": True, "install_hint": "", "configured": False},
                {"name": "piper", "available": True, "description": "Piper neural TTS", "platform_ok": True, "install_hint": "", "configured": True},
            ],
            "stt": [
                {"name": "parakeet", "available": True, "description": "Parakeet v3", "platform_ok": True, "install_hint": "", "configured": True},
            ],
        },
        "loading": {"active": False, "models": []},
    }
    return status

class TestStatusOnline:
    """Test status command when engine is running."""

    def test_shows_running(self) -> None:
        """Status shows 'running' when engine is reachable."""
        mock_client = MagicMock()
        mock_client.get_status.return_value = _mock_status()

        with patch("openvip.Client", return_value=mock_client):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "running" in result.stdout

    def test_shows_engine_info(self) -> None:
        """Status displays STT, TTS, and agent info."""
        mock_client = MagicMock()
        mock_client.get_status.return_value = _mock_status()

        with patch("openvip.Client", return_value=mock_client):
            result = runner.invoke(app, ["status"])
            assert "parakeet-v3" in result.stdout
            assert "piper" in result.stdout
            assert "claude" in result.stdout

    def test_json_output(self) -> None:
        """--json flag produces valid JSON with 'online: true'."""
        mock_client = MagicMock()
        mock_client.get_status.return_value = _mock_status()

        with patch("openvip.Client", return_value=mock_client):
            result = runner.invoke(app, ["status", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["online"] is True
            assert "platform" in data

class TestStatusOffline:
    """Test status command when engine is not running."""

    def test_shows_offline(self) -> None:
        """Status shows 'offline' when engine is unreachable."""
        with patch("openvip.Client", side_effect=ConnectionRefusedError):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "offline" in result.stdout

    def test_offline_shows_engines(self) -> None:
        """Offline status still shows engine availability."""
        with patch("openvip.Client", side_effect=ConnectionRefusedError):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "TTS Engines" in result.stdout
            assert "STT Engines" in result.stdout

    def test_offline_json(self) -> None:
        """--json in offline mode produces valid JSON with 'online: false'."""
        with patch("openvip.Client", side_effect=ConnectionRefusedError):
            result = runner.invoke(app, ["status", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["online"] is False
            assert "engines" in data
