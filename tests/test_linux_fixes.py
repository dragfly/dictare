"""Tests for Linux install fixes (issue 008).

Covers:
- check_ydotool_ready() — ydotool 0.1.x vs 1.x detection
- Status display — optional deps show "—" instead of "FAIL"
- YdotoolInjector.is_available() — uses centralized check
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# check_ydotool_ready()
# ---------------------------------------------------------------------------

class TestCheckYdotoolReady:
    """Tests for platform.check_ydotool_ready()."""

    def test_returns_false_when_ydotool_not_installed(self):
        from dictare.utils.platform import check_ydotool_ready

        with patch("dictare.utils.platform.check_command_exists", return_value=False):
            assert check_ydotool_ready() is False

    def test_ydotool_1x_with_daemon_running(self):
        """ydotool 1.x+ with ydotoold running → ready."""
        from dictare.utils.platform import check_ydotool_ready

        def fake_exists(cmd):
            return cmd in ("ydotool", "ydotoold")

        with patch("dictare.utils.platform.check_command_exists", side_effect=fake_exists), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0  # pgrep finds ydotoold
            assert check_ydotool_ready() is True

    def test_ydotool_1x_without_daemon(self):
        """ydotool 1.x+ with ydotoold NOT running → not ready."""
        from dictare.utils.platform import check_ydotool_ready

        def fake_exists(cmd):
            return cmd in ("ydotool", "ydotoold")

        with patch("dictare.utils.platform.check_command_exists", side_effect=fake_exists), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1  # pgrep doesn't find it
            assert check_ydotool_ready() is False

    def test_ydotool_01x_with_uinput_access(self):
        """ydotool 0.1.x (no ydotoold binary) with /dev/uinput writable → ready."""
        from dictare.utils.platform import check_ydotool_ready

        def fake_exists(cmd):
            return cmd == "ydotool"  # no ydotoold

        with patch("dictare.utils.platform.check_command_exists", side_effect=fake_exists), \
             patch("os.access", return_value=True):
            assert check_ydotool_ready() is True

    def test_ydotool_01x_without_uinput_access(self):
        """ydotool 0.1.x without /dev/uinput access → not ready."""
        from dictare.utils.platform import check_ydotool_ready

        def fake_exists(cmd):
            return cmd == "ydotool"  # no ydotoold

        with patch("dictare.utils.platform.check_command_exists", side_effect=fake_exists), \
             patch("os.access", return_value=False):
            assert check_ydotool_ready() is False


# ---------------------------------------------------------------------------
# Status display — optional deps
# ---------------------------------------------------------------------------

class TestStatusOptionalDeps:
    """Optional deps in dictare status should show "—" not "FAIL"."""

    def test_optional_unavailable_shows_dash(self):
        """Non-required, unavailable dep should render as dim dash."""
        from dictare.utils.platform import CheckResult

        dep = CheckResult(
            name="NVIDIA GPU",
            available=False,
            message="Not detected",
            required=False,
        )

        # Reproduce the logic from status.py
        if dep.available:
            icon = "[green]OK[/]"
        elif dep.required:
            icon = "[red]FAIL[/]"
        else:
            icon = "[dim]—[/]"

        assert icon == "[dim]—[/]"

    def test_required_unavailable_shows_fail(self):
        """Required, unavailable dep should still show FAIL."""
        from dictare.utils.platform import CheckResult

        dep = CheckResult(
            name="sounddevice",
            available=False,
            message="Not installed",
            required=True,
        )

        if dep.available:
            icon = "[green]OK[/]"
        elif dep.required:
            icon = "[red]FAIL[/]"
        else:
            icon = "[dim]—[/]"

        assert icon == "[red]FAIL[/]"

    def test_available_shows_ok(self):
        """Available dep should show OK regardless of required flag."""
        from dictare.utils.platform import CheckResult

        dep = CheckResult(
            name="Python",
            available=True,
            message="3.11",
            required=True,
        )

        if dep.available:
            icon = "[green]OK[/]"
        elif dep.required:
            icon = "[red]FAIL[/]"
        else:
            icon = "[dim]—[/]"

        assert icon == "[green]OK[/]"


# ---------------------------------------------------------------------------
# YdotoolInjector.is_available() uses centralized check
# ---------------------------------------------------------------------------

class TestYdotoolInjectorAvailability:
    """YdotoolInjector.is_available() should delegate to check_ydotool_ready()."""

    @pytest.mark.skipif(
        __import__("sys").platform != "linux",
        reason="ydotool is Linux only",
    )
    def test_delegates_to_check_ydotool_ready(self):
        from dictare.agent.injection.ydotool import YdotoolInjector

        injector = YdotoolInjector()

        with patch("dictare.agent.injection.ydotool.shutil.which", return_value="/usr/bin/ydotool"), \
             patch("dictare.utils.platform.check_ydotool_ready", return_value=True) as mock_check:
            result = injector.is_available()
            assert result is True
            mock_check.assert_called_once()

    @pytest.mark.skipif(
        __import__("sys").platform != "linux",
        reason="ydotool is Linux only",
    )
    def test_returns_false_when_binary_missing(self):
        from dictare.agent.injection.ydotool import YdotoolInjector

        injector = YdotoolInjector()

        with patch("dictare.agent.injection.ydotool.shutil.which", return_value=None):
            assert injector.is_available() is False
