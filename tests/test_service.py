"""Tests for system service management (launchd/systemd) and .app bundle."""

from __future__ import annotations

import plistlib
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from voxtype.daemon.app_bundle import (
    APP_NAME,
    BUNDLE_ID,
    create_app_bundle,
    get_app_path,
    get_executable_path,
    remove_app_bundle,
)
from voxtype.daemon.launchd import (
    LABEL,
    generate_plist,
    get_plist_path,
    is_installed,
)
from voxtype.daemon.systemd import generate_unit, get_unit_path
from voxtype.daemon.systemd import is_installed as systemd_is_installed

# ---------------------------------------------------------------------------
# .app bundle
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestAppBundleCreate:
    def test_creates_directory_structure(self, tmp_path, monkeypatch):
        monkeypatch.setattr("voxtype.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        app_path = create_app_bundle("/usr/bin/python3")
        assert (app_path / "Contents" / "Info.plist").exists()
        assert (app_path / "Contents" / "MacOS" / APP_NAME).exists()
        assert (app_path / "Contents" / "Resources").exists()

    def test_info_plist_contents(self, tmp_path, monkeypatch):
        monkeypatch.setattr("voxtype.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        app_path = create_app_bundle("/usr/bin/python3")
        with open(app_path / "Contents" / "Info.plist", "rb") as f:
            plist = plistlib.load(f)
        assert plist["CFBundleIdentifier"] == BUNDLE_ID
        assert plist["CFBundleName"] == APP_NAME
        assert plist["LSUIElement"] is True
        assert plist["CFBundleIconFile"] == APP_NAME

    def test_launcher_is_executable(self, tmp_path, monkeypatch):
        monkeypatch.setattr("voxtype.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        app_path = create_app_bundle("/opt/brew/bin/python3.11")
        launcher = app_path / "Contents" / "MacOS" / APP_NAME
        assert launcher.stat().st_mode & stat.S_IEXEC
        # python_path config file always written (used by both native and bash)
        python_path_file = app_path / "Contents" / "MacOS" / "python_path"
        assert python_path_file.read_text().strip() == "/opt/brew/bin/python3.11"

    def test_replaces_existing_bundle(self, tmp_path, monkeypatch):
        monkeypatch.setattr("voxtype.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        create_app_bundle("/usr/bin/python3")
        create_app_bundle("/other/python")
        python_path_file = tmp_path / "Test.app" / "Contents" / "MacOS" / "python_path"
        assert python_path_file.read_text().strip() == "/other/python"


@pytest.mark.slow
class TestAppBundleRemove:
    def test_removes_bundle(self, tmp_path, monkeypatch):
        monkeypatch.setattr("voxtype.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        create_app_bundle("/usr/bin/python3")
        assert (tmp_path / "Test.app").exists()
        remove_app_bundle()
        assert not (tmp_path / "Test.app").exists()

    def test_noop_if_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr("voxtype.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        remove_app_bundle()  # Should not raise


class TestAppBundlePaths:
    def test_app_path(self):
        path = get_app_path()
        assert path.name == "Voxtype.app"
        assert path.parent == Path.home() / "Applications"

    def test_executable_path(self):
        exe = get_executable_path()
        assert exe.endswith(f"Contents/MacOS/{APP_NAME}")
        assert "Voxtype.app" in exe


# ---------------------------------------------------------------------------
# launchd
# ---------------------------------------------------------------------------


class TestLaunchdGeneratePlist:
    def test_valid_xml(self):
        xml = generate_plist("/usr/bin/python3")
        parsed = plistlib.loads(xml.encode())
        assert parsed["Label"] == LABEL

    def test_fallback_when_no_app_bundle(self, monkeypatch):
        """Without .app bundle, plist uses raw python path."""
        monkeypatch.setattr(
            "voxtype.daemon.app_bundle.get_app_path",
            lambda: Path("/tmp/nonexistent/Voxtype.app"),
        )
        xml = generate_plist("/opt/venv/bin/python")
        parsed = plistlib.loads(xml.encode())
        assert parsed["ProgramArguments"][0] == "/opt/venv/bin/python"

    def test_uses_app_bundle_when_exists(self, tmp_path, monkeypatch):
        """With .app bundle, plist points to the bundle executable."""
        app_path = tmp_path / "Voxtype.app"
        app_path.mkdir()
        monkeypatch.setattr("voxtype.daemon.app_bundle.get_app_path", lambda: app_path)
        monkeypatch.setattr(
            "voxtype.daemon.app_bundle.get_executable_path",
            lambda: str(app_path / "Contents" / "MacOS" / "Voxtype"),
        )
        xml = generate_plist("/usr/bin/python3")
        parsed = plistlib.loads(xml.encode())
        assert str(app_path) in parsed["ProgramArguments"][0]

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

    def test_no_env_vars(self):
        xml = generate_plist("/usr/bin/python3")
        parsed = plistlib.loads(xml.encode())
        assert "EnvironmentVariables" not in parsed


class TestLaunchdPaths:
    def test_plist_path_in_launch_agents(self):
        path = get_plist_path()
        assert path.parent.name == "LaunchAgents"
        assert path.name == f"{LABEL}.plist"
        assert "Library" in str(path)


class TestLaunchdIsInstalled:
    def test_not_installed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "voxtype.daemon.launchd.get_plist_path",
            lambda: tmp_path / "nonexistent.plist",
        )
        assert is_installed() is False

    def test_installed(self, tmp_path, monkeypatch):
        plist = tmp_path / "test.plist"
        plist.write_text("<plist/>")
        monkeypatch.setattr(
            "voxtype.daemon.launchd.get_plist_path",
            lambda: plist,
        )
        assert is_installed() is True


# ---------------------------------------------------------------------------
# systemd
# ---------------------------------------------------------------------------


class TestSystemdGenerateUnit:
    def test_contains_exec_start(self):
        unit = generate_unit("/usr/bin/python3")
        assert "ExecStart=/usr/bin/python3 -m voxtype serve" in unit

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

    def test_restart_always(self):
        unit = generate_unit("/usr/bin/python3")
        assert "Restart=always" in unit

    def test_restart_burst_limit(self):
        unit = generate_unit("/usr/bin/python3")
        assert "StartLimitIntervalSec=60" in unit
        assert "StartLimitBurst=5" in unit


class TestSystemdPaths:
    def test_unit_path_in_systemd_user(self):
        path = get_unit_path()
        assert path.parent.name == "user"
        assert path.name == "voxtype.service"
        assert ".config/systemd/user" in str(path)


class TestSystemdIsInstalled:
    def test_not_installed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "voxtype.daemon.systemd.get_unit_path",
            lambda: tmp_path / "nonexistent.service",
        )
        assert systemd_is_installed() is False

    def test_installed(self, tmp_path, monkeypatch):
        unit = tmp_path / "test.service"
        unit.write_text("[Unit]\n")
        monkeypatch.setattr(
            "voxtype.daemon.systemd.get_unit_path",
            lambda: unit,
        )
        assert systemd_is_installed() is True


# ---------------------------------------------------------------------------
# PID writing in _run_daemon
# ---------------------------------------------------------------------------


class TestDaemonPidWrite:
    """Test that _run_daemon writes and cleans up the PID file."""

    @pytest.fixture(autouse=True)
    def _reset_voxtype_logger(self):
        """Clear voxtype logger handlers before and after each test.

        _run_daemon calls setup_logging() which attaches a FileHandler to the
        global voxtype logger. Without cleanup, that handler persists across
        test modules and writes subsequent log output to the (now deleted) temp file.
        """
        import logging
        voxtype_logger = logging.getLogger("voxtype")
        original_handlers = voxtype_logger.handlers[:]
        yield
        for h in voxtype_logger.handlers[:]:
            h.close()
        voxtype_logger.handlers[:] = original_handlers

    def test_pid_written_and_cleaned_up(self, tmp_path):
        from voxtype.cli.serve import _run_serve as _run_daemon

        pid_file = tmp_path / "engine.pid"
        log_file = tmp_path / "engine.jsonl"

        # Mock get_pid_path at the source module (imported locally inside _run_daemon)
        with patch("voxtype.utils.paths.get_pid_path", return_value=pid_file), \
             patch("voxtype.logging.setup.get_default_log_path", return_value=log_file):
            controller = MagicMock()
            controller.run.side_effect = KeyboardInterrupt

            config = SimpleNamespace(
                server=SimpleNamespace(host="127.0.0.1", port=9999),
                daemon=SimpleNamespace(restore_listening=False),
            )
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

        from voxtype.cli.serve import _run_serve as _run_daemon

        pid_file = tmp_path / "engine.pid"
        log_file = tmp_path / "engine.jsonl"

        with patch("voxtype.utils.paths.get_pid_path", return_value=pid_file), \
             patch("voxtype.logging.setup.get_default_log_path", return_value=log_file):
            controller = MagicMock()
            controller.start.side_effect = RuntimeError("boom")

            config = SimpleNamespace(
                server=SimpleNamespace(host="127.0.0.1", port=9999),
                daemon=SimpleNamespace(restore_listening=False),
            )
            mock_os = MagicMock()
            mock_os.getpid.return_value = 99999

            with pytest.raises(Exit):
                _run_daemon(controller, config, mock_os)

            # PID file should be cleaned up on failure
            assert not pid_file.exists()
