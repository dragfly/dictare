"""Tests for the Dictare-owned runtime store."""

from __future__ import annotations

from pathlib import Path

from dictare import runtime_store


def _patch_store(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(runtime_store, "RUNTIME_ROOT", root)
    monkeypatch.setattr(runtime_store, "VERSIONS_DIR", root / "versions")
    monkeypatch.setattr(runtime_store, "CURRENT_LINK", root / "current")
    monkeypatch.setattr(runtime_store, "PREVIOUS_LINK", root / "previous")
    monkeypatch.setattr(runtime_store, "LOCK_DIR", root / "locks")
    monkeypatch.setattr(runtime_store, "BIN_DIR", root.parent / "bin")
    monkeypatch.setattr(runtime_store, "SHIM_PATH", root.parent / "bin" / "dictare")


def test_activate_runtime_sets_current_and_previous(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "share" / "dictare"
    _patch_store(monkeypatch, root)

    first = root / "versions" / "1.0.0"
    second = root / "versions" / "1.0.1"
    (first / "bin").mkdir(parents=True)
    (second / "bin").mkdir(parents=True)
    (first / "bin" / "dictare").write_text("")
    (second / "bin" / "dictare").write_text("")

    runtime_store.activate_runtime(first)
    assert runtime_store.current_runtime() == first
    assert runtime_store.previous_runtime() is None

    runtime_store.activate_runtime(second)
    assert runtime_store.current_runtime() == second
    assert runtime_store.previous_runtime() == first


def test_rollback_flips_to_previous(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "share" / "dictare"
    _patch_store(monkeypatch, root)

    first = root / "versions" / "1.0.0"
    second = root / "versions" / "1.0.1"
    (first / "bin").mkdir(parents=True)
    (second / "bin").mkdir(parents=True)

    runtime_store.activate_runtime(first)
    runtime_store.activate_runtime(second)

    rolled_back = runtime_store.rollback_runtime()

    assert rolled_back == first
    assert runtime_store.current_runtime() == first
    assert runtime_store.previous_runtime() == second


def test_install_runtime_refreshes_package_index(tmp_path: Path, monkeypatch) -> None:
    """install_runtime must bypass a stale uv index cache for dictare itself."""
    root = tmp_path / "share" / "dictare"
    _patch_store(monkeypatch, root)

    runtime = root / "versions" / "1.2.3"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin" / "python").write_text("")

    commands: list[list[str]] = []
    monkeypatch.setattr(runtime_store, "_run", lambda cmd: commands.append(cmd))
    monkeypatch.setattr(runtime_store, "smoke_test", lambda *a, **k: None)

    runtime_store.install_runtime("1.2.3", extras=[])

    (install_cmd,) = commands
    refresh_idx = install_cmd.index("--refresh-package")
    assert install_cmd[refresh_idx + 1] == "dictare"
    assert install_cmd[-1] == "dictare==1.2.3"


def test_package_spec_uses_explicit_extras() -> None:
    assert runtime_store.package_spec("1.2.3", extras=["tray", "gpu"]) == (
        "dictare[tray,gpu]==1.2.3"
    )


def test_resolve_service_python_prefers_current_runtime(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "share" / "dictare"
    _patch_store(monkeypatch, root)
    runtime = root / "versions" / "1.0.0"
    (runtime / "bin").mkdir(parents=True)
    python = runtime / "bin" / "python"
    python.write_text("")

    runtime_store.activate_runtime(runtime)

    assert runtime_store.resolve_service_python_path("/fallback/python") == str(python)
