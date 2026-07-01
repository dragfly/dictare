"""CLI registration tests for runtime lifecycle commands."""

from __future__ import annotations

from typer.testing import CliRunner

from dictare.cli.__init__ import app
from dictare.cli.upgrade import _version_from_path


def test_runtime_lifecycle_commands_are_registered() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "repair" in result.output
    assert "upgrade" in result.output
    assert "rollback" in result.output
    assert "uninstall" in result.output


def test_version_from_path_parses_wheel_version() -> None:
    assert _version_from_path("dist/dictare-0.5.1rc1-py3-none-any.whl") == "0.5.1rc1"


def test_version_from_path_parses_sdist_version() -> None:
    assert _version_from_path("dist/dictare-0.5.1rc1.tar.gz") == "0.5.1rc1"


def test_version_from_path_parses_zip_version() -> None:
    assert _version_from_path("dist/dictare-0.5.1rc1.zip") == "0.5.1rc1"


def test_version_from_path_rejects_unknown_filename() -> None:
    assert _version_from_path("dist/not-dictare-0.5.1rc1-py3-none-any.whl") is None
