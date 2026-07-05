"""Tests for the per-folder session name registry."""

from __future__ import annotations

from pathlib import Path

from dictare.agent import session_registry


def _patch_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_registry, "REGISTRY_DIR", tmp_path / "projects")


class TestRecordAndLookup:
    def test_lookup_missing_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        _patch_dir(monkeypatch, tmp_path)
        assert session_registry.lookup("/some/folder", "prova") is None

    def test_record_then_lookup(self, tmp_path: Path, monkeypatch) -> None:
        _patch_dir(monkeypatch, tmp_path)
        session_registry.record_launch("/some/folder", "prova", "codex")

        entry = session_registry.lookup("/some/folder", "prova")
        assert entry is not None
        assert entry["profile"] == "codex"
        assert entry["launches"] == 1
        assert entry["last_used"]

    def test_relaunch_increments_and_rebinds_profile(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _patch_dir(monkeypatch, tmp_path)
        session_registry.record_launch("/f", "prova", "codex")
        session_registry.record_launch("/f", "prova", "claude")

        entry = session_registry.lookup("/f", "prova")
        assert entry is not None
        assert entry["profile"] == "claude"
        assert entry["launches"] == 2

    def test_same_name_different_folder_is_unrelated(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _patch_dir(monkeypatch, tmp_path)
        session_registry.record_launch("/folder/a", "prova", "codex")

        assert session_registry.lookup("/folder/b", "prova") is None

    def test_corrupt_registry_is_ignored(self, tmp_path: Path, monkeypatch) -> None:
        _patch_dir(monkeypatch, tmp_path)
        session_registry.record_launch("/f", "prova", "codex")
        session_registry._registry_path("/f").write_text("{not json")

        assert session_registry.lookup("/f", "prova") is None
        # And recording over a corrupt file recovers
        session_registry.record_launch("/f", "prova", "gemini")
        entry = session_registry.lookup("/f", "prova")
        assert entry is not None and entry["profile"] == "gemini"

    def test_record_never_raises_on_unwritable_dir(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        blocker = tmp_path / "projects"
        blocker.write_text("a file, not a dir")
        _patch_dir(monkeypatch, tmp_path)

        session_registry.record_launch("/f", "prova", "codex")  # must not raise
        assert session_registry.lookup("/f", "prova") is None


class TestListEntries:
    def test_sorted_most_recent_first(self, tmp_path: Path, monkeypatch) -> None:
        _patch_dir(monkeypatch, tmp_path)
        session_registry.record_launch("/f", "old", "codex")
        # Force distinct ordering regardless of timestamp resolution
        registry_path = session_registry._registry_path("/f")
        import json

        data = json.loads(registry_path.read_text())
        data["old"]["last_used"] = "2020-01-01T00:00:00+00:00"
        registry_path.write_text(json.dumps(data))
        session_registry.record_launch("/f", "new", "claude")

        names = [name for name, _ in session_registry.list_entries("/f")]
        assert names == ["new", "old"]

    def test_empty_folder(self, tmp_path: Path, monkeypatch) -> None:
        _patch_dir(monkeypatch, tmp_path)
        assert session_registry.list_entries("/nowhere") == []
