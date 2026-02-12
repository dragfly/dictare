"""Tests for system service management (launchd/systemd)."""

from __future__ import annotations

import plistlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from voxtype.service.launchd import (
    LABEL,
    generate_plist,
    get_plist_path,
    is_installed,
)
from voxtype.service.systemd import generate_unit, get_unit_path
from voxtype.service.systemd import is_installed as systemd_is_installed

# ---------------------------------------------------------------------------
# launchd
# ---------------------------------------------------------------------------

class TestLaunchdGeneratePlist:
    def test_valid_xml(self):
        xml = generate_plist("/usr/bin/python3")
        parsed = plistlib.loads(xml.encode())
        assert parsed["Label"] == LABEL

    def test_contains_python_path(self):
        xml = generate_plist("/opt/venv/bin/python")
        parsed = plistlib.loads(xml.encode())
        assert parsed["ProgramArguments"][0] == "/opt/venv/bin/python"

    def test_program_arguments(self):
        xml = generate_plist("/usr/bin/python3")
        parsed = plistlib.loads(xml.encode())
        args = parsed["ProgramArguments"]
        assert args == ["/usr/bin/python3", "-m", "voxtype", "engine", "start", "-d", "--agents"]

    def test_run_at_load(self):
        xml = generate_plist("/usr/bin/python3")
        parsed = plistlib.loads(xml.encode())
        assert parsed["RunAtLoad"] is True

    def test_keep_alive(self):
        xml = generate_plist("/usr/bin/python3")
        parsed = plistlib.loads(xml.encode())
        assert parsed["KeepAlive"] is True

    def test_log_paths(self):
        xml = generate_plist("/usr/bin/python3")
        parsed = plistlib.loads(xml.encode())
        assert "stdout.log" in parsed["StandardOutPath"]
        assert "stderr.log" in parsed["StandardErrorPath"]

class TestLaunchdPaths:
    def test_plist_path_in_launch_agents(self):
        path = get_plist_path()
        assert path.parent.name == "LaunchAgents"
        assert path.name == f"{LABEL}.plist"
        assert "Library" in str(path)

class TestLaunchdIsInstalled:
    def test_not_installed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "voxtype.service.launchd.get_plist_path",
            lambda: tmp_path / "nonexistent.plist",
        )
        assert is_installed() is False

    def test_installed(self, tmp_path, monkeypatch):
        plist = tmp_path / "test.plist"
        plist.write_text("<plist/>")
        monkeypatch.setattr(
            "voxtype.service.launchd.get_plist_path",
            lambda: plist,
        )
        assert is_installed() is True

# ---------------------------------------------------------------------------
# systemd
# ---------------------------------------------------------------------------

class TestSystemdGenerateUnit:
    def test_contains_exec_start(self):
        unit = generate_unit("/usr/bin/python3")
        assert "ExecStart=/usr/bin/python3 -m voxtype engine start -d --agents" in unit

    def test_contains_service_section(self):
        unit = generate_unit("/usr/bin/python3")
        assert "[Service]" in unit
        assert "[Unit]" in unit
        assert "[Install]" in unit

    def test_type_simple(self):
        unit = generate_unit("/usr/bin/python3")
        assert "Type=simple" in unit

    def test_wanted_by_default_target(self):
        unit = generate_unit("/usr/bin/python3")
        assert "WantedBy=default.target" in unit

    def test_restart_on_failure(self):
        unit = generate_unit("/usr/bin/python3")
        assert "Restart=on-failure" in unit

class TestSystemdPaths:
    def test_unit_path_in_systemd_user(self):
        path = get_unit_path()
        assert path.parent.name == "user"
        assert path.name == "voxtype.service"
        assert ".config/systemd/user" in str(path)

class TestSystemdIsInstalled:
    def test_not_installed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "voxtype.service.systemd.get_unit_path",
            lambda: tmp_path / "nonexistent.service",
        )
        assert systemd_is_installed() is False

    def test_installed(self, tmp_path, monkeypatch):
        unit = tmp_path / "test.service"
        unit.write_text("[Unit]\n")
        monkeypatch.setattr(
            "voxtype.service.systemd.get_unit_path",
            lambda: unit,
        )
        assert systemd_is_installed() is True

# ---------------------------------------------------------------------------
# PID writing in _run_daemon
# ---------------------------------------------------------------------------

class TestDaemonPidWrite:
    """Test that _run_daemon writes and cleans up the PID file."""

    def test_pid_written_and_cleaned_up(self, tmp_path):
        from voxtype.cli.engine import _run_daemon

        pid_file = tmp_path / "engine.pid"

        # Mock get_pid_path at the source module (imported locally inside _run_daemon)
        with patch("voxtype.utils.paths.get_pid_path", return_value=pid_file):
            controller = MagicMock()
            controller.run.side_effect = KeyboardInterrupt

            config = SimpleNamespace(server=SimpleNamespace(host="127.0.0.1", port=9999))
            mock_os = MagicMock()
            mock_os.getpid.return_value = 12345
            mock_os._exit.side_effect = SystemExit(0)

            with pytest.raises(SystemExit):
                _run_daemon(controller, config, mock_os)

            # PID file was written then cleaned in finally
            assert not pid_file.exists()
            controller.start.assert_called_once()
            controller.stop.assert_called_once()

    def test_pid_cleaned_on_start_failure(self, tmp_path):
        from click.exceptions import Exit

        from voxtype.cli.engine import _run_daemon

        pid_file = tmp_path / "engine.pid"

        with patch("voxtype.utils.paths.get_pid_path", return_value=pid_file):
            controller = MagicMock()
            controller.start.side_effect = RuntimeError("boom")

            config = SimpleNamespace(server=SimpleNamespace(host="127.0.0.1", port=9999))
            mock_os = MagicMock()
            mock_os.getpid.return_value = 99999

            with pytest.raises(Exit):
                _run_daemon(controller, config, mock_os)

            # PID file should be cleaned up on failure
            assert not pid_file.exists()
