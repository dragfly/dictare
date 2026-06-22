"""CLI registration tests for runtime lifecycle commands."""

from __future__ import annotations

from typer.testing import CliRunner

from dictare.cli.__init__ import app


def test_runtime_lifecycle_commands_are_registered() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "repair" in result.output
    assert "upgrade" in result.output
    assert "rollback" in result.output
