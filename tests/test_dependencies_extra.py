"""Tests for CLI dependencies module — check and resolve commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dictare.cli.dependencies import (
    _check_dependencies_internal,
    _display_dependencies,
    app,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Mock dependency result
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(
        self,
        name: str,
        available: bool,
        required: bool,
        message: str = "",
        install_hint: str | None = None,
    ) -> None:
        self.name = name
        self.available = available
        self.required = required
        self.message = message
        self.install_hint = install_hint


# ---------------------------------------------------------------------------
# _check_dependencies_internal
# ---------------------------------------------------------------------------

class TestCheckDependenciesInternal:
    """Test _check_dependencies_internal helper."""

    def test_all_ok(self) -> None:
        results = [
            _FakeResult("audio", True, True),
            _FakeResult("gpu", True, False),
        ]
        with patch("dictare.utils.platform.check_dependencies", return_value=results):
            res, all_ok, missing, optional = _check_dependencies_internal()
        assert all_ok is True
        assert missing == []
        assert optional == []

    def test_missing_required(self) -> None:
        results = [
            _FakeResult("audio", False, True, install_hint="brew install portaudio"),
        ]
        with patch("dictare.utils.platform.check_dependencies", return_value=results):
            res, all_ok, missing, optional = _check_dependencies_internal()
        assert all_ok is False
        assert len(missing) == 1

    def test_optional_missing(self) -> None:
        results = [
            _FakeResult("audio", True, True),
            _FakeResult("gpu", False, False, install_hint="pip install torch"),
        ]
        with patch("dictare.utils.platform.check_dependencies", return_value=results):
            res, all_ok, missing, optional = _check_dependencies_internal()
        assert all_ok is True
        assert len(optional) == 1

    def test_missing_without_hint(self) -> None:
        results = [
            _FakeResult("audio", False, True, install_hint=None),
        ]
        with patch("dictare.utils.platform.check_dependencies", return_value=results):
            res, all_ok, missing, optional = _check_dependencies_internal()
        assert all_ok is False
        assert missing == []  # no hint → not in list


# ---------------------------------------------------------------------------
# _display_dependencies
# ---------------------------------------------------------------------------

class TestDisplayDependencies:
    """Test _display_dependencies output."""

    def test_all_ok_output(self, capsys) -> None:
        results = [_FakeResult("audio", True, True, "OK")]
        _display_dependencies(results, True, [], [])
        # Should not raise

    def test_missing_output(self, capsys) -> None:
        missing = [_FakeResult("audio", False, True, install_hint="brew install portaudio")]
        results = [missing[0]]
        _display_dependencies(results, False, missing, [])
        # Should not raise

    def test_gpu_hint_shown(self, capsys) -> None:
        gpu = _FakeResult("Apple Silicon", False, False, install_hint="pip install mlx")
        results = [_FakeResult("audio", True, True)]
        _display_dependencies(results, True, [], [gpu])
        # Should not raise


# ---------------------------------------------------------------------------
# deps_check CLI command
# ---------------------------------------------------------------------------

class TestDepsCheckCommand:
    """Test `dictare dependencies check` command."""

    def test_all_ok_exits_0(self) -> None:
        results = [_FakeResult("audio", True, True)]
        with patch(
            "dictare.cli.dependencies._check_dependencies_internal",
            return_value=(results, True, [], []),
        ):
            result = runner.invoke(app, ["check"])
        assert result.exit_code == 0

    def test_missing_exits_1(self) -> None:
        missing = [_FakeResult("audio", False, True, install_hint="brew install portaudio")]
        with patch(
            "dictare.cli.dependencies._check_dependencies_internal",
            return_value=([missing[0]], False, missing, []),
        ):
            result = runner.invoke(app, ["check"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# deps_resolve CLI command
# ---------------------------------------------------------------------------

class TestDepsResolveCommand:
    """Test `dictare dependencies resolve` command."""

    def test_all_satisfied(self) -> None:
        results = [_FakeResult("audio", True, True)]
        with patch(
            "dictare.cli.dependencies._check_dependencies_internal",
            return_value=(results, True, [], []),
        ):
            result = runner.invoke(app, ["resolve"])
        assert result.exit_code == 0
        assert "already satisfied" in result.output

    def test_dry_run(self) -> None:
        missing = [_FakeResult("audio", False, True, install_hint="brew install portaudio")]
        with patch(
            "dictare.cli.dependencies._check_dependencies_internal",
            return_value=([missing[0]], False, missing, []),
        ):
            result = runner.invoke(app, ["resolve", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.output

    def test_no_commands_available(self) -> None:
        missing = [_FakeResult("audio", False, True, install_hint=None)]
        with patch(
            "dictare.cli.dependencies._check_dependencies_internal",
            return_value=([missing[0]], False, [], []),
        ):
            result = runner.invoke(app, ["resolve"])
        # all_ok=False but no resolvable items
        assert result.exit_code == 0 or "already satisfied" in result.output or "No automatic" in result.output

    def test_resolve_runs_commands(self) -> None:
        missing = [_FakeResult("audio", False, True, install_hint="echo test")]
        # First call: stuff missing; second call (re-check): all ok
        call_count = [0]

        def side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return ([missing[0]], False, missing, [])
            return ([_FakeResult("audio", True, True)], True, [], [])

        with (
            patch(
                "dictare.cli.dependencies._check_dependencies_internal",
                side_effect=side_effect,
            ),
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
        ):
            result = runner.invoke(app, ["resolve"])
        assert "All dependencies are now satisfied" in result.output

    def test_resolve_command_fails(self) -> None:
        missing = [_FakeResult("audio", False, True, install_hint="false")]
        call_count = [0]

        def side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return ([missing[0]], False, missing, [])
            return ([missing[0]], False, missing, [])

        with (
            patch(
                "dictare.cli.dependencies._check_dependencies_internal",
                side_effect=side_effect,
            ),
            patch("subprocess.run", return_value=MagicMock(returncode=1)),
        ):
            result = runner.invoke(app, ["resolve"])
        assert result.exit_code == 1
