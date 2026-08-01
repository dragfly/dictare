"""Tests for per-agent session adapters (named session continuity phase 2)."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from dictare.agent import session_adapters, session_registry
from dictare.agent.session_adapters import get_adapter


class TestGetAdapter:
    def test_known_binaries(self) -> None:
        for binary in ("claude", "codex", "gemini", "pi", "aider"):
            assert get_adapter(binary) is not None

    def test_full_path_resolves_basename(self) -> None:
        assert get_adapter("/opt/homebrew/bin/claude") is not None

    def test_unknown_binary(self) -> None:
        assert get_adapter("some-future-agent") is None


class TestClaudeAdapter:
    def test_new_session_assigns_uuid_and_name(self) -> None:
        plan = get_adapter("claude").new_session("/f", "prova")
        assert plan.extra_args[0] == "--session-id"
        assert str(uuid.UUID(plan.extra_args[1]))  # valid uuid
        assert plan.extra_args[2:] == ["--name", "prova"]
        assert plan.binding == {"session_id": plan.extra_args[1]}

    def test_resume_by_bound_uuid(self) -> None:
        adapter = get_adapter("claude")
        assert adapter.resume_args({"session_id": "abc"}) == ["--resume", "abc"]
        assert adapter.resume_args({}) is None


class TestGeminiAdapter:
    def test_new_session_assigns_uuid(self) -> None:
        plan = get_adapter("gemini").new_session("/f", "prova")
        assert plan.extra_args[0] == "--session-id"
        assert plan.binding == {"session_id": plan.extra_args[1]}

    def test_resume(self) -> None:
        adapter = get_adapter("gemini")
        assert adapter.resume_args({"session_id": "u1"}) == ["--resume", "u1"]
        assert adapter.resume_args({}) is None


class TestAiderAdapter:
    def test_new_and_resume_use_same_owned_history_file(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(session_registry, "REGISTRY_DIR", tmp_path)
        monkeypatch.setattr(session_adapters, "REGISTRY_DIR", tmp_path)

        adapter = get_adapter("aider")
        plan = adapter.new_session("/f", "prova")
        assert plan.extra_args[0] == "--chat-history-file"
        assert "--restore-chat-history" in plan.extra_args
        assert plan.binding["session_path"] == plan.extra_args[1]

        resume = adapter.resume_args(plan.binding)
        assert resume == plan.extra_args

    def test_resume_unbound(self) -> None:
        assert get_adapter("aider").resume_args({}) is None


def _write_session_file(
    path: Path, header: dict, mtime: float | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(header) + "\n")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


class TestPiAdapter:
    def test_discover_binds_newest_file_for_cwd(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        adapter = get_adapter("pi")
        monkeypatch.setattr(type(adapter), "SESSIONS_ROOT", tmp_path)
        now = time.time()
        _write_session_file(
            tmp_path / "enc-a" / "s1.jsonl", {"cwd": "/folder/a"}, now + 1
        )
        _write_session_file(
            tmp_path / "enc-b" / "s2.jsonl", {"cwd": "/folder/b"}, now + 2
        )

        binding = adapter.discover_binding("/folder/a", now)
        assert binding == {"session_path": str(tmp_path / "enc-a" / "s1.jsonl")}

    def test_discover_ignores_files_before_launch(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        adapter = get_adapter("pi")
        monkeypatch.setattr(type(adapter), "SESSIONS_ROOT", tmp_path)
        now = time.time()
        _write_session_file(
            tmp_path / "enc" / "old.jsonl", {"cwd": "/f"}, now - 100
        )

        assert adapter.discover_binding("/f", now) == {}

    def test_resume_requires_existing_file(self, tmp_path: Path) -> None:
        adapter = get_adapter("pi")
        real = tmp_path / "s.jsonl"
        real.write_text("{}\n")
        assert adapter.resume_args({"session_path": str(real)}) == [
            "--session",
            str(real),
        ]
        assert adapter.resume_args({"session_path": str(tmp_path / "gone")}) is None


class TestCodexAdapter:
    def test_discover_prefers_header_id_and_checks_cwd(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        adapter = get_adapter("codex")
        monkeypatch.setattr(type(adapter), "SESSIONS_ROOT", tmp_path)
        now = time.time()
        sid = "019f1f48-47d6-7bc3-8217-adfcbdd68318"
        _write_session_file(
            tmp_path / "2026" / "07" / "03" / f"rollout-2026-07-03T10-00-00-{sid}.jsonl",
            {"payload": {"session_id": sid, "cwd": "/folder/a"}},
            now + 1,
        )
        other = "029f1f48-47d6-7bc3-8217-adfcbdd68319"
        _write_session_file(
            tmp_path / "2026" / "07" / "03" / f"rollout-2026-07-03T10-00-01-{other}.jsonl",
            {"payload": {"session_id": other, "cwd": "/folder/b"}},
            now + 2,
        )

        assert adapter.discover_binding("/folder/a", now) == {"session_id": sid}

    def test_resume_uses_subcommand(self) -> None:
        adapter = get_adapter("codex")
        assert adapter.resume_args({"session_id": "u1"}) == ["resume", "u1"]
        assert adapter.resume_args({}) is None

    def test_new_session_has_no_extra_args(self) -> None:
        plan = get_adapter("codex").new_session("/f", "prova")
        assert plan.extra_args == [] and plan.binding == {}


class TestRegistryBindingLifecycle:
    def test_binding_survives_relaunch_same_profile(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(session_registry, "REGISTRY_DIR", tmp_path)
        session_registry.record_launch("/f", "prova", "codex")
        session_registry.update_entry("/f", "prova", {"session_id": "u1"})
        session_registry.record_launch("/f", "prova", "codex")

        entry = session_registry.lookup("/f", "prova")
        assert entry is not None and entry["session_id"] == "u1"

    def test_binding_dropped_on_profile_rebind(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(session_registry, "REGISTRY_DIR", tmp_path)
        session_registry.record_launch("/f", "prova", "codex")
        session_registry.update_entry("/f", "prova", {"session_id": "u1"})
        session_registry.record_launch("/f", "prova", "claude")

        entry = session_registry.lookup("/f", "prova")
        assert entry is not None and "session_id" not in entry

    def test_update_entry_noop_for_missing_name(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(session_registry, "REGISTRY_DIR", tmp_path)
        session_registry.update_entry("/f", "ghost", {"session_id": "u1"})
        assert session_registry.lookup("/f", "ghost") is None
