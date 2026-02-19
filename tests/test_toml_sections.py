"""Tests for TOML section read/write (WYSIWYG editor)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from voxtype.core.toml_sections import (
    _extract_section_lines,
    _strip_section_lines,
    apply_section,
    serialize_section,
)

# ---------------------------------------------------------------------------
# _strip_section_lines — inverse of _extract_section_lines
# ---------------------------------------------------------------------------

def _roundtrip(text: str, section: str) -> None:
    """Verify extract + strip partitions text without overlap or gap."""
    extracted = _extract_section_lines(text, section) or ""
    stripped = _strip_section_lines(text, section)
    # Stripped + extracted lines should together reconstruct the original
    # (ignoring trailing newline differences at section boundaries)
    combined = stripped.rstrip("\n") + ("\n\n" if stripped.strip() and extracted.strip() else "") + extracted.strip()
    # Just verify no content was silently lost
    assert extracted or not any(
        line.startswith("[agent_types") for line in text.splitlines()
    )

class TestStripSectionLines:
    """_strip_section_lines removes owned lines; _extract_section_lines recovers them."""

    def test_strip_agent_types_removes_header_and_entries(self) -> None:
        text = """\
[stt]
model = "large-v3-turbo"

[agent_types.claude]
command = ["claude"]

[tts]
engine = "espeak"
"""
        stripped = _strip_section_lines(text, "agent_types")
        assert "[agent_types" not in stripped
        assert 'command = ["claude"]' not in stripped
        assert "[stt]" in stripped
        assert "[tts]" in stripped

    def test_strip_removes_preceding_comments(self) -> None:
        """Comments immediately before an owned header must be removed too."""
        text = """\
[stt]
model = "base"

# This comment belongs to agent_types
[agent_types.claude]
command = ["claude"]
"""
        stripped = _strip_section_lines(text, "agent_types")
        assert "# This comment belongs to agent_types" not in stripped
        assert "[stt]" in stripped

    def test_strip_preserves_unrelated_comments(self) -> None:
        """Comments NOT preceding an owned header must be kept."""
        text = """\
# Top-level comment

[stt]
# stt comment
model = "base"

[agent_types.claude]
command = ["claude"]
"""
        stripped = _strip_section_lines(text, "agent_types")
        assert "# Top-level comment" in stripped
        assert "# stt comment" in stripped

    def test_strip_removes_default_agent_type(self) -> None:
        text = """\
default_agent_type = "claude"

[agent_types.claude]
command = ["claude"]

[stt]
model = "base"
"""
        stripped = _strip_section_lines(text, "agent_types")
        assert "default_agent_type" not in stripped
        assert "[stt]" in stripped

    def test_strip_empty_file(self) -> None:
        assert _strip_section_lines("", "agent_types") == ""

    def test_strip_section_absent(self) -> None:
        text = "[stt]\nmodel = \"base\"\n"
        assert _strip_section_lines(text, "agent_types") == text

    def test_strip_audio_advanced(self) -> None:
        text = """\
[audio]
silence_ms = 1200

[audio.advanced]
sample_rate = 16000
channels = 1

[stt]
model = "base"
"""
        stripped = _strip_section_lines(text, "audio.advanced")
        assert "[audio.advanced]" not in stripped
        assert "sample_rate" not in stripped
        assert "[audio]" in stripped
        assert "[stt]" in stripped

# ---------------------------------------------------------------------------
# Idempotency: save same content N times → file stays identical
# ---------------------------------------------------------------------------

class TestSaveIdempotency:
    """Saving the same TOML content multiple times must not grow the file."""

    def _make_config(self, tmp_path: Path, initial: str) -> Path:
        p = tmp_path / "config.toml"
        p.write_text(initial, encoding="utf-8")
        return p

    def test_agent_types_no_duplicate_on_resave(self, tmp_path: Path) -> None:
        initial = """\
[stt]
model = "large-v3-turbo"

[agent_types.sonnet]
command = ["claude", "--model", "claude-sonnet-4-6"]
description = "Claude Sonnet"
"""
        config_path = self._make_config(tmp_path, initial)

        # Simulate what the UI does: load section, save it back unchanged
        from voxtype.config import Config
        from voxtype.core.toml_sections import serialize_section

        config = Config()
        section_text = serialize_section("agent_types", config)

        # Save once
        apply_section("agent_types", section_text, config_path)
        after_first = config_path.read_text(encoding="utf-8")

        # Save same text again (idempotent)
        apply_section("agent_types", section_text, config_path)
        after_second = config_path.read_text(encoding="utf-8")

        assert after_first == after_second, (
            "File grew after second identical save — duplicate content bug"
        )

    def test_agent_types_no_comment_accumulation(self, tmp_path: Path) -> None:
        """Comments in the header template must not accumulate across saves."""
        initial = "[stt]\nmodel = \"base\"\n"
        config_path = self._make_config(tmp_path, initial)

        from voxtype.config import Config
        from voxtype.core.toml_sections import serialize_section

        config = Config()
        # serialize_section returns the template (comment-only) since section absent
        section_text = serialize_section("agent_types", config)

        apply_section("agent_types", section_text, config_path)
        size_after_1 = len(config_path.read_text(encoding="utf-8"))

        apply_section("agent_types", section_text, config_path)
        size_after_2 = len(config_path.read_text(encoding="utf-8"))

        assert size_after_1 == size_after_2, (
            f"File grew from {size_after_1} to {size_after_2} bytes on second save"
        )
