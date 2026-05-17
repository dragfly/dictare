"""Regression tests for project packaging metadata."""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mlx_extra_pins_release_tested_stack() -> None:
    """Homebrew sdist installs must not drift away from the tested MLX stack."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    mlx_deps = pyproject["project"]["optional-dependencies"]["mlx"]
    assert "mlx==0.30.4" in mlx_deps
    assert "mlx-whisper==0.4.3" in mlx_deps
    assert "mlx-audio==0.3.0" in mlx_deps


def test_lockfile_matches_release_tested_mlx_stack() -> None:
    """The committed lockfile should resolve the same MLX stack."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    packages = {pkg["name"]: pkg["version"] for pkg in lock["package"] if "version" in pkg}

    assert packages["mlx"] == "0.30.4"
    assert packages["mlx-whisper"] == "0.4.3"
    assert packages["mlx-audio"] == "0.3.0"
