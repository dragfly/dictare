"""Tests for self-healing python_path resolution.

After `brew upgrade`, the Cellar path changes (e.g. 0.2.0 → 0.2.1).
resolve_python_path() decides which path to use; ensure_python_path()
writes it to disk. The logic is pure — no SO calls, fully testable.
"""

from __future__ import annotations

from dictare.daemon.app_bundle import resolve_python_path


class TestResolvePythonPath:
    """Test the pure decision logic — no filesystem, no mocks."""

    # -- First install (no stored path) --

    def test_no_stored_path_returns_current(self) -> None:
        path, changed = resolve_python_path("/brew/0.2.0/bin/python", None)
        assert path == "/brew/0.2.0/bin/python"
        assert changed is True

    # -- Path unchanged (normal restart) --

    def test_same_path_no_change(self) -> None:
        path, changed = resolve_python_path(
            "/brew/0.2.0/bin/python",
            "/brew/0.2.0/bin/python",
        )
        assert path == "/brew/0.2.0/bin/python"
        assert changed is False

    # -- Brew upgrade (version changed) --

    def test_version_changed_returns_current(self) -> None:
        path, changed = resolve_python_path(
            "/brew/0.2.1/bin/python",
            "/brew/0.2.0/bin/python",
        )
        assert path == "/brew/0.2.1/bin/python"
        assert changed is True

    def test_beta_to_stable_upgrade(self) -> None:
        path, changed = resolve_python_path(
            "/brew/0.2.1/bin/python",
            "/brew/0.2.1b2/bin/python",
        )
        assert path == "/brew/0.2.1/bin/python"
        assert changed is True

    def test_stable_to_beta_downgrade(self) -> None:
        path, changed = resolve_python_path(
            "/brew/0.2.1b3/bin/python",
            "/brew/0.2.1/bin/python",
        )
        assert path == "/brew/0.2.1b3/bin/python"
        assert changed is True

    # -- Path completely different (pyenv → brew, or manual change) --

    def test_pyenv_to_brew(self) -> None:
        path, changed = resolve_python_path(
            "/opt/homebrew/Cellar/dictare/0.2.0/libexec/uv-tools/dictare/bin/python",
            "/Users/twister/.pyenv/versions/3.11.7/bin/python3.11",
        )
        assert path == "/opt/homebrew/Cellar/dictare/0.2.0/libexec/uv-tools/dictare/bin/python"
        assert changed is True

    def test_brew_to_dev_venv(self) -> None:
        path, changed = resolve_python_path(
            "/Users/twister/repos/dictare/.venv/bin/python",
            "/opt/homebrew/Cellar/dictare/0.2.0/libexec/uv-tools/dictare/bin/python",
        )
        assert path == "/Users/twister/repos/dictare/.venv/bin/python"
        assert changed is True

    # -- Edge cases --

    def test_empty_stored_path_treated_as_changed(self) -> None:
        path, changed = resolve_python_path("/brew/0.2.0/bin/python", "")
        assert path == "/brew/0.2.0/bin/python"
        assert changed is True

    def test_whitespace_stored_path_treated_as_changed(self) -> None:
        path, changed = resolve_python_path("/brew/0.2.0/bin/python", "  ")
        assert path == "/brew/0.2.0/bin/python"
        assert changed is True
