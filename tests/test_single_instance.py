"""Tests for single-instance enforcement (PID file + port check)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voxtype.app.controller import AppController
from voxtype.config import Config

def _make_controller() -> AppController:
    return AppController(config=MagicMock(spec=Config))

class TestPidFileCheck:
    """AppController._check_single_instance() — PID file logic."""

    def test_no_pid_file_writes_pid(self, tmp_path: Path) -> None:
        """First start: no PID file → creates one with current PID."""
        pid_path = tmp_path / "engine.pid"
        ctrl = _make_controller()

        with (
            patch("voxtype.app.controller.atexit.register"),
            patch("voxtype.utils.paths.get_pid_path", return_value=pid_path),
            patch("voxtype.utils.paths.get_voxtype_dir", return_value=tmp_path),
        ):
            ctrl._check_single_instance()

        assert pid_path.exists()
        assert pid_path.read_text().strip() == str(os.getpid())

    def test_stale_pid_file_is_replaced(self, tmp_path: Path) -> None:
        """Stale PID (process gone) → old file removed, new PID written."""
        pid_path = tmp_path / "engine.pid"
        pid_path.write_text("999999999")  # Extremely unlikely to exist

        ctrl = _make_controller()
        with (
            patch("voxtype.app.controller.atexit.register"),
            patch("voxtype.utils.paths.get_pid_path", return_value=pid_path),
            patch("voxtype.utils.paths.get_voxtype_dir", return_value=tmp_path),
        ):
            ctrl._check_single_instance()

        assert pid_path.read_text().strip() == str(os.getpid())

    def test_live_pid_raises(self, tmp_path: Path) -> None:
        """Live PID (current process) → RuntimeError raised."""
        pid_path = tmp_path / "engine.pid"
        pid_path.write_text(str(os.getpid()))  # Our own PID — definitely alive

        ctrl = _make_controller()
        with (
            patch("voxtype.utils.paths.get_pid_path", return_value=pid_path),
            patch("voxtype.utils.paths.get_voxtype_dir", return_value=tmp_path),
        ):
            with pytest.raises(RuntimeError, match="already running"):
                ctrl._check_single_instance()

    def test_cleanup_pid_removes_own_file(self, tmp_path: Path) -> None:
        """_cleanup_pid() removes the file only if it contains our PID."""
        pid_path = tmp_path / "engine.pid"
        pid_path.write_text(str(os.getpid()))

        ctrl = _make_controller()
        with patch("voxtype.utils.paths.get_pid_path", return_value=pid_path):
            ctrl._cleanup_pid()

        assert not pid_path.exists()

    def test_cleanup_pid_leaves_foreign_pid(self, tmp_path: Path) -> None:
        """_cleanup_pid() does NOT remove a file written by a different process."""
        pid_path = tmp_path / "engine.pid"
        pid_path.write_text("1")  # PID 1 (init/systemd) — not us

        ctrl = _make_controller()
        with patch("voxtype.utils.paths.get_pid_path", return_value=pid_path):
            ctrl._cleanup_pid()

        assert pid_path.exists()

    def test_cleanup_pid_missing_file_is_safe(self, tmp_path: Path) -> None:
        """_cleanup_pid() with no PID file is a no-op."""
        pid_path = tmp_path / "engine.pid"
        ctrl = _make_controller()
        with patch("voxtype.utils.paths.get_pid_path", return_value=pid_path):
            ctrl._cleanup_pid()  # Should not raise
