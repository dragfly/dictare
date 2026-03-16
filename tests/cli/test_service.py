"""Tests for service management CLI commands (dictare.cli.service)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import typer

from dictare.cli.service import (
    _get_backend,
    service_restart,
    service_start,
    service_status,
    service_stop,
    service_uninstall,
)

# ---------------------------------------------------------------------------
# _get_backend
# ---------------------------------------------------------------------------

class TestGetBackend:
    def test_returns_launchd_on_darwin(self) -> None:
        with patch("dictare.cli.service.sys") as mock_sys:
            mock_sys.platform = "darwin"
            backend = _get_backend()
        assert hasattr(backend, "install")

    def test_returns_systemd_on_linux(self) -> None:
        with patch("dictare.cli.service.sys") as mock_sys:
            mock_sys.platform = "linux"
            backend = _get_backend()
        assert hasattr(backend, "install")

    def test_raises_on_unsupported_platform(self) -> None:
        with patch("dictare.cli.service.sys") as mock_sys, \
             patch("dictare.cli.service.console"):
            mock_sys.platform = "win32"
            with pytest.raises(typer.Exit):
                _get_backend()


# ---------------------------------------------------------------------------
# service_install — tested via typer CliRunner
# ---------------------------------------------------------------------------

class TestServiceInstallViaCli:
    def test_install_invokes_backend(self) -> None:
        from typer.testing import CliRunner

        from dictare.cli.service import app

        runner = CliRunner()
        mock_backend = MagicMock()

        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.sys") as mock_sys, \
             patch("dictare.config.get_config_path", return_value=mock_config_path), \
             patch("dictare.cli.service.console"):
            mock_sys.platform = "darwin"
            runner.invoke(app, ["install"])

        mock_backend.install.assert_called_once()

    def test_install_failure_exits_nonzero(self) -> None:
        from typer.testing import CliRunner

        from dictare.cli.service import app

        runner = CliRunner()
        mock_backend = MagicMock()
        mock_backend.install.side_effect = RuntimeError("failed")

        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.sys") as mock_sys, \
             patch("dictare.config.get_config_path", return_value=mock_config_path), \
             patch("dictare.cli.service.console"):
            mock_sys.platform = "darwin"
            result = runner.invoke(app, ["install"])

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# service_uninstall
# ---------------------------------------------------------------------------

class TestServiceUninstall:
    def test_uninstall_when_installed(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            service_uninstall()

        mock_backend.uninstall.assert_called_once()

    def test_uninstall_when_not_installed(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = False

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            with pytest.raises(typer.Exit):
                service_uninstall()

    def test_uninstall_failure_raises_exit(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True
        mock_backend.uninstall.side_effect = RuntimeError("failed")

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            with pytest.raises(typer.Exit):
                service_uninstall()


# ---------------------------------------------------------------------------
# service_start
# ---------------------------------------------------------------------------

class TestServiceStart:
    def test_start_when_installed(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            service_start()

        mock_backend.start.assert_called_once()

    def test_start_when_not_installed(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = False

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            with pytest.raises(typer.Exit):
                service_start()

    def test_start_failure_raises_exit(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True
        mock_backend.start.side_effect = RuntimeError("boom")

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            with pytest.raises(typer.Exit):
                service_start()


# ---------------------------------------------------------------------------
# service_stop
# ---------------------------------------------------------------------------

class TestServiceStop:
    def test_stop_when_installed(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            service_stop()

        mock_backend.stop.assert_called_once()

    def test_stop_when_not_installed(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = False

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            with pytest.raises(typer.Exit):
                service_stop()


# ---------------------------------------------------------------------------
# service_restart
# ---------------------------------------------------------------------------

class TestServiceRestart:
    def test_restart_calls_stop_then_start(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True
        call_order: list[str] = []
        mock_backend.stop.side_effect = lambda: call_order.append("stop")
        mock_backend.start.side_effect = lambda: call_order.append("start")

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            service_restart()

        assert call_order == ["stop", "start"]

    def test_restart_when_not_installed(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = False

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            with pytest.raises(typer.Exit):
                service_restart()

    def test_restart_stop_failure(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True
        mock_backend.stop.side_effect = RuntimeError("stop failed")

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            with pytest.raises(typer.Exit):
                service_restart()

    def test_restart_start_failure(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True
        mock_backend.start.side_effect = RuntimeError("start failed")

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            with pytest.raises(typer.Exit):
                service_restart()


# ---------------------------------------------------------------------------
# service_status
# ---------------------------------------------------------------------------

class TestServiceStatus:
    def test_status_not_installed(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = False

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            with pytest.raises(typer.Exit):
                service_status()

    def test_status_not_loaded(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True
        mock_backend.is_loaded.return_value = False

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"):
            service_status()  # should not raise

    def test_status_engine_running(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True
        mock_backend.is_loaded.return_value = True

        mock_status = MagicMock()
        mock_status.platform = {"mode": "listening", "version": "1.0.0"}
        mock_client = MagicMock()
        mock_client.get_status.return_value = mock_status

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"), \
             patch("dictare.config.load_config") as mock_load, \
             patch("openvip.Client", return_value=mock_client):
            mock_load.return_value = SimpleNamespace(
                server=SimpleNamespace(host="127.0.0.1", port=9999)
            )
            service_status()

    def test_status_engine_not_responding(self) -> None:
        mock_backend = MagicMock()
        mock_backend.is_installed.return_value = True
        mock_backend.is_loaded.return_value = True

        with patch("dictare.cli.service._get_backend", return_value=mock_backend), \
             patch("dictare.cli.service.console"), \
             patch("dictare.config.load_config") as mock_load, \
             patch("openvip.Client", side_effect=ConnectionRefusedError):
            mock_load.return_value = SimpleNamespace(
                server=SimpleNamespace(host="127.0.0.1", port=9999)
            )
            service_status()  # should not raise
