"""Tests for code quality fixes (bare except tightening, magic numbers, etc.).

Regression tests to ensure tightened exception handlers still catch the
expected errors and that extracted constants are used correctly.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dictare.core.http_server import OpenVIPServer

# ---------------------------------------------------------------------------
# Shared fixtures (same pattern as test_tts_worker.py)
# ---------------------------------------------------------------------------

class _MockTTSMgr:
    def __init__(self) -> None:
        self._tts_proxy = None

    def complete_tts(self, message_id: str, *, ok: bool, duration_ms: int = 0) -> None:
        if self._tts_proxy is not None:
            self._tts_proxy.complete(message_id, ok=ok, duration_ms=duration_ms)

class MockEngine:
    RESERVED_AGENT_IDS = {"__keyboard__", "__tts__"}
    TTS_AGENT_ID = "__tts__"

    def __init__(self) -> None:
        self._registered_agents: list = []
        self._unregistered_agents: list[str] = []
        self._tts_mgr = _MockTTSMgr()

    def register_agent(self, agent) -> bool:
        self._registered_agents.append(agent)
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        self._unregistered_agents.append(agent_id)
        return True

    def get_status(self) -> dict:
        return {"protocol_version": "1.0", "state": "idle", "connected_agents": []}

    def complete_tts(self, message_id: str, *, ok: bool, duration_ms: int = 0) -> None:
        self._tts_mgr.complete_tts(message_id, ok=ok, duration_ms=duration_ms)

@pytest.fixture
def engine() -> MockEngine:
    return MockEngine()

@pytest.fixture
def token() -> str:
    return "test-token-abc123"

@pytest.fixture
def server(engine: MockEngine, token: str) -> OpenVIPServer:
    return OpenVIPServer(
        engine, None,
        host="127.0.0.1", port=0,
        auth_tokens={"register_tts": token},
    )

@pytest.fixture
def client(server: OpenVIPServer) -> TestClient:
    return TestClient(server._app)

# ---------------------------------------------------------------------------
# I2: Bare except tightening — HTTP JSON parse
# ---------------------------------------------------------------------------

class TestJSONParseExceptionType:
    """Verify that invalid JSON returns 422 (tightened from except Exception)."""

    def test_invalid_json_speech_returns_422(self, client: TestClient) -> None:
        """POST /speech with invalid JSON body → 422."""
        response = client.post(
            "/speech",
            content=b"not json at all {{{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert "invalid JSON" in response.json()["detail"]

    def test_invalid_json_agent_message_returns_422(
        self, client: TestClient, server: OpenVIPServer, token: str,
    ) -> None:
        """POST /agents/{id}/messages with invalid JSON → 422."""
        import asyncio

        # Create agent queue so endpoint doesn't 404
        queue: asyncio.Queue = asyncio.Queue()
        with server._agent_queues_lock:
            server._agent_queues["test-agent"] = queue

        response = client.post(
            "/agents/test-agent/messages",
            content=b"<<<not json>>>",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert "invalid JSON" in response.json()["detail"]

# ---------------------------------------------------------------------------
# I2: Bare except tightening — TTS manager
# ---------------------------------------------------------------------------

class TestTTSManagerExceptionTypes:
    """Verify tightened exception types in TTSManager."""

    def test_stop_kills_on_timeout(self) -> None:
        """stop() calls kill() when wait() raises TimeoutExpired."""
        from dictare.core.tts_manager import TTSManager

        mock_config = MagicMock()
        mgr = TTSManager(mock_config)

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)
        mgr._tts_worker_process = mock_proc

        mgr.stop()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert mgr._tts_worker_process is None

    def test_load_tts_phrases_handles_invalid_json(self, tmp_path: Path) -> None:
        """_load_tts_phrases returns defaults on invalid JSON."""
        from dictare.core.tts_manager import TTSManager

        phrases_file = tmp_path / "tts_phrases.json"
        phrases_file.write_text("{invalid json!!!")

        with patch("pathlib.Path.home", return_value=tmp_path / "fake_home"):
            # Create the expected path structure
            config_dir = tmp_path / "fake_home" / ".config" / "dictare"
            config_dir.mkdir(parents=True)
            bad_file = config_dir / "tts_phrases.json"
            bad_file.write_text("{not valid json")

            result = TTSManager._load_tts_phrases()

        # Should return defaults, not crash
        assert isinstance(result, dict)
        assert "agent" in result

    def test_load_tts_phrases_handles_missing_file(self) -> None:
        """_load_tts_phrases returns defaults when file doesn't exist."""
        from dictare.core.tts_manager import TTSManager

        result = TTSManager._load_tts_phrases()
        assert isinstance(result, dict)
        assert "agent" in result

    def test_list_voices_handles_timeout(self) -> None:
        """_list_voices_via_venv returns [] on subprocess timeout."""
        from dictare.core.tts_manager import TTSManager

        with patch(
            "dictare.tts.venv.get_venv_python",
            return_value="/fake/python",
        ):
            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="test", timeout=30),
            ):
                result = TTSManager._list_voices_via_venv("kokoro")

        assert result == []

    def test_list_voices_handles_os_error(self) -> None:
        """_list_voices_via_venv returns [] on OSError."""
        from dictare.core.tts_manager import TTSManager

        with patch(
            "dictare.tts.venv.get_venv_python",
            return_value="/fake/python",
        ):
            with patch(
                "subprocess.run",
                side_effect=FileNotFoundError("/fake/python"),
            ):
                result = TTSManager._list_voices_via_venv("kokoro")

        assert result == []

# ---------------------------------------------------------------------------
# I3: Magic numbers — verify constants exist and are used
# ---------------------------------------------------------------------------

class TestMagicNumberConstants:
    """Verify extracted constants exist with expected values."""

    def test_beep_constants(self) -> None:
        from dictare.audio.beep import (
            _FALLBACK_CMD_TIMEOUT,
            _PLAYBACK_DEADLINE_S,
            _PLAYBACK_POLL_S,
        )

        assert _PLAYBACK_DEADLINE_S == 10.0
        assert _PLAYBACK_POLL_S == 0.05
        assert _FALLBACK_CMD_TIMEOUT == 5

    def test_controller_constants(self) -> None:
        from dictare.core.controller import _QUEUE_POLL_S, _WORKER_JOIN_TIMEOUT

        assert _QUEUE_POLL_S == 0.1
        assert _WORKER_JOIN_TIMEOUT == 1.0

    def test_tts_manager_constants(self) -> None:
        from dictare.core.tts_manager import (
            _TTS_WORKER_CONNECT_TIMEOUT,
            _TTS_WORKER_STOP_TIMEOUT,
        )

        assert _TTS_WORKER_CONNECT_TIMEOUT == 120.0
        assert _TTS_WORKER_STOP_TIMEOUT == 5.0

    def test_http_server_constants(self) -> None:
        from dictare.core.http_server import (
            _JOB_CLEANUP_DELAY,
            _SERVER_JOIN_TIMEOUT,
        )

        assert _SERVER_JOIN_TIMEOUT == 0.5
        assert _JOB_CLEANUP_DELAY == 10.0

# ---------------------------------------------------------------------------
# I2: Audio capture — silent exception now logs
# ---------------------------------------------------------------------------

class TestAudioCaptureLogging:
    """Verify audio device query failures are logged."""

    def test_get_default_device_logs_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """get_default_device logs debug message on exception."""
        from dictare.audio.capture import AudioCapture

        with patch("sounddevice.default", new=MagicMock()) as mock_default:
            mock_default.device = [0]
            with patch(
                "sounddevice.query_devices",
                side_effect=RuntimeError("device gone"),
            ):
                import logging

                with caplog.at_level(logging.DEBUG, logger="dictare.audio.capture"):
                    result = AudioCapture.get_default_device()

        assert result is None
        assert any("default input device" in r.message for r in caplog.records)

# ---------------------------------------------------------------------------
# Metaphone — verify CC comment exists (documentation check)
# ---------------------------------------------------------------------------

class TestMetaphoneDocumentation:
    """Verify metaphone has the CC documentation note."""

    def test_metaphone_docstring_mentions_cc(self) -> None:
        from dictare.utils.jellyfish import metaphone

        assert "CC=62" in (metaphone.__doc__ or "")
        assert "not meant to be refactored" in (metaphone.__doc__ or "")
