"""Tests for system service management (launchd/systemd) and .app bundle."""

from __future__ import annotations

import plistlib
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from dictare.daemon.app_bundle import (
    APP_NAME,
    BUNDLE_ID,
    create_app_bundle,
    get_app_path,
    get_executable_path,
    remove_app_bundle,
)
from dictare.daemon.launchd import (
    LABEL,
    _get_service_pid,
    _kill_orphan_processes,
    _stop_service,
    _wait_for_process_exit,
    generate_plist,
    get_plist_path,
    is_installed,
)
from dictare.daemon.systemd import generate_unit, get_unit_path
from dictare.daemon.systemd import is_installed as systemd_is_installed

# ---------------------------------------------------------------------------
# .app bundle
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestAppBundleCreate:
    def test_creates_directory_structure(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dictare.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        app_path = create_app_bundle("/usr/bin/python3")
        assert (app_path / "Contents" / "Info.plist").exists()
        assert (app_path / "Contents" / "MacOS" / APP_NAME).exists()
        assert (app_path / "Contents" / "Resources").exists()

    def test_info_plist_contents(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dictare.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        app_path = create_app_bundle("/usr/bin/python3")
        with open(app_path / "Contents" / "Info.plist", "rb") as f:
            plist = plistlib.load(f)
        assert plist["CFBundleIdentifier"] == BUNDLE_ID
        assert plist["CFBundleName"] == APP_NAME
        assert plist["LSUIElement"] is True
        assert plist["CFBundleIconFile"] == APP_NAME

    def test_launcher_is_executable(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dictare.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        app_path = create_app_bundle("/opt/brew/bin/python3.11")
        launcher = app_path / "Contents" / "MacOS" / APP_NAME
        assert launcher.stat().st_mode & stat.S_IEXEC
        # python_path written externally to ~/.dictare/python_path (not inside bundle)
        python_path_file = Path.home() / ".dictare" / "python_path"
        assert python_path_file.read_text().strip() == "/opt/brew/bin/python3.11"

    def test_replaces_existing_bundle(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dictare.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        create_app_bundle("/usr/bin/python3")
        create_app_bundle("/other/python")
        # python_path written externally, not inside bundle
        python_path_file = Path.home() / ".dictare" / "python_path"
        assert python_path_file.read_text().strip() == "/other/python"

@pytest.mark.slow
class TestAppBundleRemove:
    def test_removes_bundle(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dictare.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        create_app_bundle("/usr/bin/python3")
        assert (tmp_path / "Test.app").exists()
        remove_app_bundle()
        assert not (tmp_path / "Test.app").exists()

    def test_noop_if_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dictare.daemon.app_bundle.get_app_path", lambda: tmp_path / "Test.app")
        remove_app_bundle()  # Should not raise

class TestAppBundlePaths:
    def test_app_path(self):
        path = get_app_path()
        assert path.name == "Dictare.app"
        assert path.parent == Path.home() / "Applications"

    def test_executable_path(self):
        exe = get_executable_path()
        assert exe.endswith(f"Contents/MacOS/{APP_NAME}")
        assert "Dictare.app" in exe

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
            "dictare.daemon.app_bundle.get_app_path",
            lambda: Path("/tmp/nonexistent/Dictare.app"),
        )
        xml = generate_plist("/opt/venv/bin/python")
        parsed = plistlib.loads(xml.encode())
        assert parsed["ProgramArguments"][0] == "/opt/venv/bin/python"

    def test_uses_app_bundle_when_exists(self, tmp_path, monkeypatch):
        """With .app bundle, plist points to the bundle executable."""
        app_path = tmp_path / "Dictare.app"
        app_path.mkdir()
        monkeypatch.setattr("dictare.daemon.app_bundle.get_app_path", lambda: app_path)
        monkeypatch.setattr(
            "dictare.daemon.app_bundle.get_executable_path",
            lambda: str(app_path / "Contents" / "MacOS" / "Dictare"),
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
            "dictare.daemon.launchd.get_plist_path",
            lambda: tmp_path / "nonexistent.plist",
        )
        assert is_installed() is False

    def test_installed(self, tmp_path, monkeypatch):
        plist = tmp_path / "test.plist"
        plist.write_text("<plist/>")
        monkeypatch.setattr(
            "dictare.daemon.launchd.get_plist_path",
            lambda: plist,
        )
        assert is_installed() is True

# ---------------------------------------------------------------------------
# launchd stop / kill verification
# ---------------------------------------------------------------------------

class TestGetServicePid:
    def test_parses_pid_from_launchctl_output(self):
        launchctl_output = (
            '{\n'
            '\t"StandardOutPath" = "/Users/x/Library/Logs/dictare/stdout.log";\n'
            '\t"Label" = "dev.dragfly.dictare";\n'
            '\t"OnDemand" = false;\n'
            '\t"PID" = 12345;\n'
            '};\n'
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(
                returncode=0, stdout=launchctl_output, stderr=""
            )
            assert _get_service_pid() == 12345

    def test_returns_none_when_not_loaded(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(
                returncode=113, stdout="", stderr=""
            )
            assert _get_service_pid() is None

    def test_returns_none_when_no_pid_line(self):
        launchctl_output = (
            '{\n'
            '\t"Label" = "dev.dragfly.dictare";\n'
            '\t"LastExitStatus" = 0;\n'
            '};\n'
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(
                returncode=0, stdout=launchctl_output, stderr=""
            )
            assert _get_service_pid() is None

class TestWaitForProcessExit:
    def test_returns_true_when_process_gone(self):
        with patch("os.kill", side_effect=ProcessLookupError):
            assert _wait_for_process_exit(99999, timeout=0.5) is True

    def test_returns_true_on_permission_error(self):
        with patch("os.kill", side_effect=PermissionError):
            assert _wait_for_process_exit(99999, timeout=0.5) is True

    def test_returns_false_when_process_survives(self):
        with patch("os.kill"):  # no exception = process alive
            assert _wait_for_process_exit(99999, timeout=0.3) is False

class TestStopService:
    def test_unloads_and_waits(self):
        with patch("dictare.daemon.launchd._get_service_pid", return_value=42), \
             patch("subprocess.run") as mock_run, \
             patch("dictare.daemon.launchd._wait_for_process_exit", return_value=True):
            _stop_service()
            mock_run.assert_called_once()
            assert "unload" in mock_run.call_args[0][0]

    def test_force_kills_surviving_process(self):
        with patch("dictare.daemon.launchd._get_service_pid", return_value=42), \
             patch("subprocess.run"), \
             patch("dictare.daemon.launchd._wait_for_process_exit", return_value=False), \
             patch("os.kill") as mock_kill:
            _stop_service()
            mock_kill.assert_called_once_with(42, 9)

    def test_handles_no_pid(self):
        with patch("dictare.daemon.launchd._get_service_pid", return_value=None), \
             patch("subprocess.run") as mock_run:
            _stop_service()
            mock_run.assert_called_once()

class TestKillOrphanProcesses:
    def test_kills_engine_by_pid_file(self, tmp_path):
        dictare_dir = tmp_path / ".dictare"
        dictare_dir.mkdir()
        pid_file = dictare_dir / "engine.pid"
        pid_file.write_text("12345\n")

        with patch("dictare.daemon.launchd.Path.home", return_value=tmp_path), \
             patch("os.kill") as mock_kill, \
             patch("subprocess.run"):
            # os.kill(pid, 0) succeeds = process alive, then os.kill(pid, 9)
            _kill_orphan_processes()
            assert mock_kill.call_count == 2
            mock_kill.assert_any_call(12345, 0)
            mock_kill.assert_any_call(12345, 9)

    def test_skips_dead_engine(self, tmp_path):
        dictare_dir = tmp_path / ".dictare"
        dictare_dir.mkdir()
        pid_file = dictare_dir / "engine.pid"
        pid_file.write_text("12345\n")

        with patch("dictare.daemon.launchd.Path.home", return_value=tmp_path), \
             patch("os.kill", side_effect=ProcessLookupError) as mock_kill, \
             patch("subprocess.run"):
            _kill_orphan_processes()
            # Only the alive-check, no SIGKILL
            mock_kill.assert_called_once_with(12345, 0)

    def test_always_pkills_launcher(self, tmp_path):
        dictare_dir = tmp_path / ".dictare"
        dictare_dir.mkdir()
        # No PID file

        with patch("dictare.daemon.launchd.Path.home", return_value=tmp_path), \
             patch("subprocess.run") as mock_run:
            _kill_orphan_processes()
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "pkill" in args
            assert "Dictare.app" in " ".join(args)

# ---------------------------------------------------------------------------
# systemd
# ---------------------------------------------------------------------------

class TestSystemdGenerateUnit:
    def test_contains_exec_start(self):
        unit = generate_unit("/usr/bin/python3")
        assert "ExecStart=/usr/bin/python3 -m dictare serve" in unit

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
        assert path.name == "dictare.service"
        assert ".config/systemd/user" in str(path)

class TestSystemdIsInstalled:
    def test_not_installed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "dictare.daemon.systemd.get_unit_path",
            lambda: tmp_path / "nonexistent.service",
        )
        assert systemd_is_installed() is False

    def test_installed(self, tmp_path, monkeypatch):
        unit = tmp_path / "test.service"
        unit.write_text("[Unit]\n")
        monkeypatch.setattr(
            "dictare.daemon.systemd.get_unit_path",
            lambda: unit,
        )
        assert systemd_is_installed() is True

# ---------------------------------------------------------------------------
# PID writing in _run_daemon
# ---------------------------------------------------------------------------

class TestDaemonPidWrite:
    """Test that _run_daemon writes and cleans up the PID file."""

    @pytest.fixture(autouse=True)
    def _reset_dictare_logger(self):
        """Clear dictare logger handlers before and after each test.

        _run_daemon calls setup_logging() which attaches a FileHandler to the
        global dictare logger. Without cleanup, that handler persists across
        test modules and writes subsequent log output to the (now deleted) temp file.
        """
        import logging
        dictare_logger = logging.getLogger("dictare")
        original_handlers = dictare_logger.handlers[:]
        yield
        for h in dictare_logger.handlers[:]:
            h.close()
        dictare_logger.handlers[:] = original_handlers

    def test_pid_written_and_cleaned_up(self, tmp_path):
        from dictare.cli.serve import _run_serve as _run_daemon

        pid_file = tmp_path / "engine.pid"
        log_file = tmp_path / "engine.jsonl"

        # Mock get_pid_path at the source module (imported locally inside _run_daemon)
        with patch("dictare.utils.paths.get_pid_path", return_value=pid_file), \
             patch("dictare.logging.setup.get_default_log_path", return_value=log_file):
            controller = MagicMock()
            controller.run.side_effect = KeyboardInterrupt

            config = SimpleNamespace(
                server=SimpleNamespace(host="127.0.0.1", port=9999),
                daemon=SimpleNamespace(restore_listening=False),
                log_level="info",
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

        from dictare.cli.serve import _run_serve as _run_daemon

        pid_file = tmp_path / "engine.pid"
        log_file = tmp_path / "engine.jsonl"

        with patch("dictare.utils.paths.get_pid_path", return_value=pid_file), \
             patch("dictare.logging.setup.get_default_log_path", return_value=log_file):
            controller = MagicMock()
            controller.start.side_effect = RuntimeError("boom")

            config = SimpleNamespace(
                server=SimpleNamespace(host="127.0.0.1", port=9999),
                daemon=SimpleNamespace(restore_listening=False),
                log_level="info",
            )
            mock_os = MagicMock()
            mock_os.getpid.return_value = 99999

            with pytest.raises(Exit):
                _run_daemon(controller, config, mock_os)

            # PID file should be cleaned up on failure
            assert not pid_file.exists()
