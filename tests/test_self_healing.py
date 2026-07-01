"""Tests for self-healing python_path resolution.

The launcher reads ``~/.dictare/python_path`` before Python starts. New installs
pin that file to Dictare's runtime store; legacy installs can still fall back to
Homebrew or the currently running development interpreter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dictare import runtime_store
from dictare.daemon import app_bundle
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


# ---------------------------------------------------------------------------
# find_brew_python — discover the Homebrew-installed dictare's venv interpreter
# ---------------------------------------------------------------------------

class TestFindBrewPython:
    """Detect the brew install by resolving `dictare` on PATH and matching the
    Cellar layout. No filesystem writes — only `shutil.which` and `Path.is_file`
    are patched. The brew prefix is intentionally not hard-coded."""

    def _set_path_layout(
        self,
        monkeypatch: pytest.MonkeyPatch,
        which_returns: str | None,
        existing_paths: set[str] | None = None,
    ) -> None:
        monkeypatch.setattr(app_bundle.shutil, "which", lambda _: which_returns)

        existing = existing_paths or set()

        def fake_resolve(self: Path, strict: bool = False) -> Path:  # noqa: ARG001
            return self

        def fake_is_file(self: Path) -> bool:
            return str(self) in existing

        monkeypatch.setattr(Path, "resolve", fake_resolve)
        monkeypatch.setattr(Path, "is_file", fake_is_file)

    def test_apple_silicon_brew_install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cellar = "/opt/homebrew/Cellar/dictare/0.2.7/libexec/bin/dictare"
        python = "/opt/homebrew/Cellar/dictare/0.2.7/libexec/uv-tools/dictare/bin/python"
        self._set_path_layout(monkeypatch, cellar, {python})
        assert app_bundle.find_brew_python() == python

    def test_stable_opt_path_wins_without_path_lookup(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        opt_python = "/opt/homebrew/opt/dictare/libexec/uv-tools/dictare/bin/python"
        self._set_path_layout(monkeypatch, None, {opt_python})
        assert app_bundle.find_brew_python() == opt_python

    def test_intel_brew_install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cellar = "/usr/local/Cellar/dictare/0.2.7/libexec/bin/dictare"
        python = "/usr/local/Cellar/dictare/0.2.7/libexec/uv-tools/dictare/bin/python"
        self._set_path_layout(monkeypatch, cellar, {python})
        assert app_bundle.find_brew_python() == python

    def test_custom_brew_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cellar = "/Users/alice/brew/Cellar/dictare/1.0.0/libexec/bin/dictare"
        python = "/Users/alice/brew/Cellar/dictare/1.0.0/libexec/uv-tools/dictare/bin/python"
        self._set_path_layout(monkeypatch, cellar, {python})
        assert app_bundle.find_brew_python() == python

    def test_dictare_not_on_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_path_layout(monkeypatch, None)
        assert app_bundle.find_brew_python() is None

    def test_dictare_is_dev_venv_not_cellar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # `which dictare` returns a path outside the Cellar (typical when a
        # .venv is active in the shell) — must return None, not misdetect.
        self._set_path_layout(
            monkeypatch,
            "/Users/dev/repo/dictare/.venv/bin/dictare",
            existing_paths={"/never/used"},
        )
        assert app_bundle.find_brew_python() is None

    def test_dictare_pyenv_install_not_misdetected(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # A pyenv shim or editable install must not be treated as a brew install.
        self._set_path_layout(
            monkeypatch,
            "/Users/dev/.pyenv/versions/3.11.7/bin/dictare",
        )
        assert app_bundle.find_brew_python() is None

    def test_brew_path_but_python_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Cellar layout matches but the expected venv python file is absent
        # (corrupted install) — return None so callers fall back gracefully.
        self._set_path_layout(
            monkeypatch,
            "/opt/homebrew/Cellar/dictare/0.2.7/libexec/bin/dictare",
            existing_paths=set(),
        )
        assert app_bundle.find_brew_python() is None


# ---------------------------------------------------------------------------
# _find_cellar_bundle — discover Homebrew's signed launcher source
# ---------------------------------------------------------------------------

class TestFindCellarBundle:
    """Find the signed Homebrew bundle without depending on PATH order."""

    def _make_bundle(self, root: Path) -> Path:
        bundle = root / "Dictare.app"
        macos = bundle / "Contents" / "MacOS"
        macos.mkdir(parents=True)
        (macos / "Dictare").write_text("")
        return bundle

    def test_env_bundle_wins_when_runtime_shim_shadows_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        bundle = self._make_bundle(tmp_path / "homebrew" / "libexec" / "bundle")
        user_shim = tmp_path / "home" / ".local" / "bin" / "dictare"
        user_shim.parent.mkdir(parents=True)
        user_shim.write_text("")

        monkeypatch.setenv("DICTARE_HOMEBREW_BUNDLE", str(bundle))
        monkeypatch.setattr(app_bundle.shutil, "which", lambda _: str(user_shim))

        assert app_bundle._find_cellar_bundle() == bundle

    def test_persistent_bundle_hint_wins_when_runtime_shim_shadows_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = tmp_path / "home"
        bundle = self._make_bundle(tmp_path / "custom-brew" / "libexec" / "bundle")
        user_shim = fake_home / ".local" / "bin" / "dictare"
        user_shim.parent.mkdir(parents=True)
        user_shim.write_text("")
        hint = fake_home / ".dictare" / "homebrew_bundle_path"
        hint.parent.mkdir(parents=True)
        hint.write_text(str(bundle))

        monkeypatch.delenv("DICTARE_HOMEBREW_BUNDLE", raising=False)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr(app_bundle.shutil, "which", lambda _: str(user_shim))

        assert app_bundle._find_cellar_bundle() == bundle


# ---------------------------------------------------------------------------
# ensure_python_path — runtime-store priority + legacy fallbacks
# ---------------------------------------------------------------------------

class TestEnsurePythonPath:
    """Integration of `find_brew_python` + write logic.

    Stored path is read from `~/.dictare/python_path`; we redirect
    `Path.home()` to a tmp dir to avoid touching the real home.
    """

    @pytest.fixture
    def fake_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        return tmp_path

    def _stored(self, fake_home: Path) -> str | None:
        f = fake_home / ".dictare" / "python_path"
        return f.read_text().strip() if f.exists() else None

    def test_runtime_store_overrides_stale_pyenv_path(
        self,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime = "/Users/dev/.local/share/dictare/versions/0.5.0rc1/bin/python"
        pyenv = "/Users/dev/.pyenv/versions/3.11.7/bin/python3.11"

        (fake_home / ".dictare").mkdir()
        (fake_home / ".dictare" / "python_path").write_text(pyenv)

        monkeypatch.setattr(runtime_store, "resolve_service_python_path", lambda fallback=None: runtime)
        app_bundle.ensure_python_path(pyenv)

        assert self._stored(fake_home) == runtime

    def test_runtime_store_no_rewrite_when_already_correct(
        self,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime = "/Users/dev/.local/share/dictare/versions/0.5.0rc1/bin/python"

        (fake_home / ".dictare").mkdir()
        (fake_home / ".dictare" / "python_path").write_text(runtime)
        before_mtime = (fake_home / ".dictare" / "python_path").stat().st_mtime_ns

        monkeypatch.setattr(runtime_store, "resolve_service_python_path", lambda fallback=None: runtime)
        app_bundle.ensure_python_path("/some/other/python")

        # Path is unchanged AND file was not rewritten.
        assert self._stored(fake_home) == runtime
        assert (fake_home / ".dictare" / "python_path").stat().st_mtime_ns == before_mtime

    def test_dev_mode_fallback_when_no_runtime_or_brew(
        self,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        venv = "/Users/dev/repo/dictare/.venv/bin/python"
        monkeypatch.setattr(runtime_store, "resolve_service_python_path", lambda fallback=None: None)
        monkeypatch.setattr(app_bundle, "find_brew_python", lambda: None)
        app_bundle.ensure_python_path(venv)
        assert self._stored(fake_home) == venv

    def test_legacy_brew_fallback_when_no_runtime(
        self,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        brew = "/opt/homebrew/Cellar/dictare/0.2.7/libexec/uv-tools/dictare/bin/python"
        monkeypatch.setattr(runtime_store, "resolve_service_python_path", lambda fallback=None: None)
        monkeypatch.setattr(app_bundle, "find_brew_python", lambda: brew)

        app_bundle.ensure_python_path("/Users/dev/.venv/bin/python")
        assert self._stored(fake_home) == brew

    def test_sync_service_python_path_repairs_stale_venv_before_launch(
        self,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime = "/Users/dev/.local/share/dictare/versions/0.5.0rc1/bin/python"
        stale = "/Users/dev/repo/dictare/.venv/bin/python"
        (fake_home / ".dictare").mkdir()
        (fake_home / ".dictare" / "python_path").write_text(stale)

        monkeypatch.setattr(runtime_store, "resolve_service_python_path", lambda fallback=None: runtime)
        resolved = app_bundle.sync_service_python_path(stale)

        assert resolved == runtime
        assert self._stored(fake_home) == runtime
