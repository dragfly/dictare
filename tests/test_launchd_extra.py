"""Additional tests for launchd module (dictare.daemon.launchd)."""

from __future__ import annotations

import plistlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dictare.daemon.launchd import (
    LABEL,
    LOG_DIR,
    TRAY_LABEL,
    get_tray_plist_path,
    install_tray,
    is_loaded,
    is_tray_installed,
    launch_at_login_enabled,
    start,
    stop,
    uninstall_tray,
)

# ---------------------------------------------------------------------------
# Tray plist paths
# ---------------------------------------------------------------------------

class TestTrayPlistPath:
    def test_tray_plist_in_launch_agents(self) -> None:
        path = get_tray_plist_path()
        assert path.parent.name == "LaunchAgents"
        assert TRAY_LABEL in path.name

    def test_tray_label_differs_from_engine(self) -> None:
        assert TRAY_LABEL != LABEL
        assert TRAY_LABEL.startswith(LABEL)


# ---------------------------------------------------------------------------
# is_loaded
# ---------------------------------------------------------------------------

class TestIsLoaded:
    def test_loaded_returns_true(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(returncode=0)
            assert is_loaded() is True

    def test_not_loaded_returns_false(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(returncode=113)
            assert is_loaded() is False


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

class TestStart:
    def test_start_loads_plist(self, tmp_path: Path) -> None:
        plist = tmp_path / "test.plist"
        plist.write_text("<plist/>")

        with patch("dictare.daemon.launchd.get_plist_path", return_value=plist), \
             patch("dictare.daemon.launchd.is_loaded", return_value=False), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(returncode=0)
            start()
            assert "load" in mock_run.call_args[0][0]

    def test_start_noop_if_already_loaded(self, tmp_path: Path) -> None:
        plist = tmp_path / "test.plist"
        plist.write_text("<plist/>")

        with patch("dictare.daemon.launchd.get_plist_path", return_value=plist), \
             patch("dictare.daemon.launchd.is_loaded", return_value=True), \
             patch("subprocess.run") as mock_run:
            start()
            mock_run.assert_not_called()

    def test_start_raises_if_not_installed(self, tmp_path: Path) -> None:
        plist = tmp_path / "nonexistent.plist"

        with patch("dictare.daemon.launchd.get_plist_path", return_value=plist):
            with pytest.raises(RuntimeError, match="not installed"):
                start()


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

class TestStop:
    def test_stop_when_loaded(self) -> None:
        with patch("dictare.daemon.launchd.is_loaded", return_value=True), \
             patch("dictare.daemon.launchd._stop_service") as mock_stop:
            stop()
            mock_stop.assert_called_once()

    def test_stop_noop_if_not_loaded(self) -> None:
        with patch("dictare.daemon.launchd.is_loaded", return_value=False), \
             patch("dictare.daemon.launchd._stop_service") as mock_stop:
            stop()
            mock_stop.assert_not_called()


# ---------------------------------------------------------------------------
# install_tray
# ---------------------------------------------------------------------------

class TestInstallTray:
    def test_install_tray_creates_plist(self, tmp_path: Path) -> None:
        plist_path = tmp_path / "tray.plist"

        with patch("dictare.daemon.launchd.get_tray_plist_path", return_value=plist_path), \
             patch("dictare.daemon.launchd.LOG_DIR", tmp_path / "logs"), \
             patch("subprocess.run") as mock_run:
            # First call: launchctl list (not loaded)
            # Second call: launchctl load
            mock_run.side_effect = [
                SimpleNamespace(returncode=113),  # not loaded
                SimpleNamespace(returncode=0),     # load
            ]
            # Mock the stable path check
            with patch("pathlib.Path.exists", return_value=False):
                install_tray()

        assert plist_path.exists()
        plist_data = plistlib.loads(plist_path.read_bytes())
        assert plist_data["Label"] == TRAY_LABEL
        assert plist_data["RunAtLoad"] is True
        assert plist_data["KeepAlive"] is False

    def test_install_tray_unloads_if_already_loaded(self, tmp_path: Path) -> None:
        plist_path = tmp_path / "tray.plist"

        with patch("dictare.daemon.launchd.get_tray_plist_path", return_value=plist_path), \
             patch("dictare.daemon.launchd.LOG_DIR", tmp_path / "logs"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                SimpleNamespace(returncode=0),   # already loaded → unload
                SimpleNamespace(returncode=0),   # unload
                SimpleNamespace(returncode=0),   # load
            ]
            with patch("pathlib.Path.exists", return_value=False):
                install_tray()

        # Should have called unload then load
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any("unload" in c for c in calls)
        assert any("load" in c for c in calls)


# ---------------------------------------------------------------------------
# uninstall_tray
# ---------------------------------------------------------------------------

class TestUninstallTray:
    def test_uninstall_tray_removes_plist(self, tmp_path: Path) -> None:
        plist_path = tmp_path / "tray.plist"
        plist_path.write_text("<plist/>")

        with patch("dictare.daemon.launchd.get_tray_plist_path", return_value=plist_path), \
             patch("subprocess.run"):
            uninstall_tray()

        assert not plist_path.exists()

    def test_uninstall_tray_noop_if_missing(self, tmp_path: Path) -> None:
        plist_path = tmp_path / "nonexistent.plist"

        with patch("dictare.daemon.launchd.get_tray_plist_path", return_value=plist_path), \
             patch("subprocess.run") as mock_run:
            uninstall_tray()
            mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# is_tray_installed
# ---------------------------------------------------------------------------

class TestIsTrayInstalled:
    def test_installed(self, tmp_path: Path) -> None:
        plist = tmp_path / "tray.plist"
        plist.write_text("<plist/>")
        with patch("dictare.daemon.launchd.get_tray_plist_path", return_value=plist):
            assert is_tray_installed() is True

    def test_not_installed(self, tmp_path: Path) -> None:
        with patch("dictare.daemon.launchd.get_tray_plist_path", return_value=tmp_path / "nope"):
            assert is_tray_installed() is False


# ---------------------------------------------------------------------------
# launch_at_login
# ---------------------------------------------------------------------------

class TestLaunchAtLogin:
    def test_enabled_when_both_installed(self) -> None:
        with patch("dictare.daemon.launchd.is_installed", return_value=True), \
             patch("dictare.daemon.launchd.is_tray_installed", return_value=True):
            assert launch_at_login_enabled() is True

    def test_disabled_when_engine_missing(self) -> None:
        with patch("dictare.daemon.launchd.is_installed", return_value=False), \
             patch("dictare.daemon.launchd.is_tray_installed", return_value=True):
            assert launch_at_login_enabled() is False

    def test_disabled_when_tray_missing(self) -> None:
        with patch("dictare.daemon.launchd.is_installed", return_value=True), \
             patch("dictare.daemon.launchd.is_tray_installed", return_value=False):
            assert launch_at_login_enabled() is False


# ---------------------------------------------------------------------------
# LOG_DIR constant
# ---------------------------------------------------------------------------

class TestLogDir:
    def test_log_dir_in_library_logs(self) -> None:
        assert "Library/Logs/dictare" in str(LOG_DIR)
