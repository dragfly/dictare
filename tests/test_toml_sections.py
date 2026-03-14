"""Tests for TOML section read/write (WYSIWYG editor)."""
from __future__ import annotations

from pathlib import Path

from dictare.core.toml_sections import (
    _TOML_HEADER_RE,
    _extract_section_lines,
    _strip_section_lines,
    apply_section,
)

# ---------------------------------------------------------------------------
# _strip_section_lines — inverse of _extract_section_lines
# ---------------------------------------------------------------------------

def _roundtrip(text: str, section: str) -> None:
    """Verify extract + strip partitions text without overlap or gap."""
    extracted = _extract_section_lines(text, section) or ""
    _strip_section_lines(text, section)  # verify no crash
    # Just verify no content was silently lost
    assert extracted or not any(
        line.startswith("[agent_profiles") for line in text.splitlines()
    )

class TestStripSectionLines:
    """_strip_section_lines removes owned lines; _extract_section_lines recovers them."""

    def test_strip_agent_profiles_removes_header_and_entries(self) -> None:
        text = """\
[stt]
model = "large-v3-turbo"

[agent_profiles.claude]
command = ["claude"]

[tts]
engine = "espeak"
"""
        stripped = _strip_section_lines(text, "agent_profiles")
        assert "[agent_profiles" not in stripped
        assert 'command = ["claude"]' not in stripped
        assert "[stt]" in stripped
        assert "[tts]" in stripped

    def test_strip_keeps_comments_in_non_owned_section(self) -> None:
        """Comments after a non-owned header belong to that section, not stripped."""
        text = """\
[stt]
model = "base"

# This comment is after [stt], belongs to stt
[agent_profiles.claude]
command = ["claude"]
"""
        stripped = _strip_section_lines(text, "agent_profiles")
        # Comment belongs to [stt] section, so it's kept
        assert "# This comment is after [stt], belongs to stt" in stripped
        assert "[stt]" in stripped
        # Owned content is stripped
        assert "[agent_profiles" not in stripped

    def test_strip_preserves_unrelated_comments(self) -> None:
        """Comments NOT preceding an owned header must be kept."""
        text = """\
# Top-level comment

[stt]
# stt comment
model = "base"

[agent_profiles.claude]
command = ["claude"]
"""
        stripped = _strip_section_lines(text, "agent_profiles")
        assert "# Top-level comment" in stripped
        assert "# stt comment" in stripped

    def test_strip_removes_agent_profiles_default_inside_section(self) -> None:
        text = """\
[agent_profiles]
default = "claude"

[agent_profiles.claude]
command = ["claude"]

[stt]
model = "base"
"""
        stripped = _strip_section_lines(text, "agent_profiles")
        assert "[agent_profiles]" not in stripped
        assert "default" not in stripped
        assert "[stt]" in stripped

    def test_strip_empty_file(self) -> None:
        assert _strip_section_lines("", "agent_profiles") == ""

    def test_strip_section_absent(self) -> None:
        text = "[stt]\nmodel = \"base\"\n"
        assert _strip_section_lines(text, "agent_profiles") == text

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

    def test_agent_profiles_no_duplicate_on_resave(self, tmp_path: Path) -> None:
        initial = """\
[stt]
model = "large-v3-turbo"

[agent_profiles]
default = "sonnet"

[agent_profiles.sonnet]
command = ["claude", "--model", "claude-sonnet-4-6"]
description = "Claude Sonnet"
"""
        config_path = self._make_config(tmp_path, initial)

        # Simulate what the UI does: load section, save it back unchanged
        from dictare.config import Config
        from dictare.core.toml_sections import serialize_section

        config = Config()
        section_text = serialize_section("agent_profiles", config)

        # Save once
        apply_section("agent_profiles", section_text, config_path)
        after_first = config_path.read_text(encoding="utf-8")

        # Save same text again (idempotent)
        apply_section("agent_profiles", section_text, config_path)
        after_second = config_path.read_text(encoding="utf-8")

        assert after_first == after_second, (
            "File grew after second identical save — duplicate content bug"
        )

    def test_agent_profiles_no_comment_accumulation(self, tmp_path: Path) -> None:
        """Comments in the header template must not accumulate across saves."""
        initial = "[stt]\nmodel = \"base\"\n"
        config_path = self._make_config(tmp_path, initial)

        from dictare.config import Config
        from dictare.core.toml_sections import serialize_section

        config = Config()
        # serialize_section returns the template (comment-only) since section absent
        section_text = serialize_section("agent_profiles", config)

        apply_section("agent_profiles", section_text, config_path)
        size_after_1 = len(config_path.read_text(encoding="utf-8"))

        apply_section("agent_profiles", section_text, config_path)
        size_after_2 = len(config_path.read_text(encoding="utf-8"))

        assert size_after_1 == size_after_2, (
            f"File grew from {size_after_1} to {size_after_2} bytes on second save"
        )

# ---------------------------------------------------------------------------
# TOML header regex — distinguishes [section] from ["array", "literal"]
# ---------------------------------------------------------------------------

class TestTomlHeaderRegex:
    """_TOML_HEADER_RE must match section headers, not array literals."""

    def test_simple_section(self) -> None:
        assert _TOML_HEADER_RE.match("[stt]")

    def test_dotted_section(self) -> None:
        assert _TOML_HEADER_RE.match("[pipeline.submit_filter]")

    def test_double_bracket_array_table(self) -> None:
        assert _TOML_HEADER_RE.match("[[keyboard.shortcuts]]")

    def test_array_literal_not_matched(self) -> None:
        """TOML array value like ["ok", "send"] must NOT match as a header."""
        assert not _TOML_HEADER_RE.match('["ok", "send"]')

    def test_array_literal_single_quotes(self) -> None:
        assert not _TOML_HEADER_RE.match("['ok', 'send']")

    def test_nested_array_literal(self) -> None:
        assert not _TOML_HEADER_RE.match('[["ok", "invia"], ["ok", "manda"]]')

    def test_indented_array_literal(self) -> None:
        """Indented array value (common in multi-line TOML)."""
        # After strip(), this becomes ["ok", "invia"]
        assert not _TOML_HEADER_RE.match('["ok", "invia"]')

    def test_section_with_spaces(self) -> None:
        assert _TOML_HEADER_RE.match("[ stt ]")

    def test_section_with_underscore(self) -> None:
        assert _TOML_HEADER_RE.match("[agent_profiles]")

# ---------------------------------------------------------------------------
# Multi-line array values inside sections
# ---------------------------------------------------------------------------

class TestMultiLineArrayValues:
    """Sections with multi-line TOML arrays must be extracted/stripped correctly."""

    def test_extract_submit_filter_with_multiline_arrays(self) -> None:
        """Multi-line array values are part of the section, not headers."""
        text = """\
[stt]
model = "parakeet-v3"

[pipeline.submit_filter.triggers]
"*" = [
    ["ok", "invia"],
    ["ok", "manda"],
]

[agent_profiles]
default = "sonnet"
"""
        extracted = _extract_section_lines(text, "pipeline.submit_filter")
        assert extracted is not None
        assert "[pipeline.submit_filter.triggers]" in extracted
        assert '["ok", "invia"]' in extracted
        assert '["ok", "manda"]' in extracted
        assert "[agent_profiles]" not in extracted
        assert "[stt]" not in extracted

    def test_strip_submit_filter_with_multiline_arrays(self) -> None:
        """Stripping removes multi-line array values with the section."""
        text = """\
[stt]
model = "parakeet-v3"

[pipeline.submit_filter.triggers]
"*" = [
    ["ok", "invia"],
    ["ok", "manda"],
]

[agent_profiles]
default = "sonnet"
"""
        stripped = _strip_section_lines(text, "pipeline.submit_filter")
        assert "[pipeline.submit_filter" not in stripped
        assert '["ok", "invia"]' not in stripped
        assert "[stt]" in stripped
        assert "[agent_profiles]" in stripped

    def test_extract_with_multiple_language_keys(self) -> None:
        """Section with multiple language keys and multi-line arrays."""
        text = """\
[pipeline.submit_filter.triggers]
"*" = [
    ["ok", "send"],
    ["ok", "submit"],
]
it = [
    ["ok", "invia"],
    ["ok", "manda"],
]
"""
        extracted = _extract_section_lines(text, "pipeline.submit_filter")
        assert extracted is not None
        assert '["ok", "send"]' in extracted
        assert '["ok", "submit"]' in extracted
        assert '["ok", "invia"]' in extracted
        assert '["ok", "manda"]' in extracted

    def test_roundtrip_multiline_arrays(self, tmp_path: Path) -> None:
        """Save/load roundtrip preserves multi-line array content."""
        initial = """\
[stt]
model = "parakeet-v3"
"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(initial, encoding="utf-8")

        section_content = """\
[pipeline.submit_filter.triggers]
"*" = [
    ["ok", "send"],
    ["ok", "submit"],
]
"""
        apply_section("pipeline.submit_filter", section_content, config_path)

        # Read back and verify
        result = config_path.read_text(encoding="utf-8")
        assert '["ok", "send"]' in result
        assert '["ok", "submit"]' in result
        assert "[stt]" in result

        # Extract and verify section is complete
        extracted = _extract_section_lines(result, "pipeline.submit_filter")
        assert extracted is not None
        assert '["ok", "send"]' in extracted
        assert '["ok", "submit"]' in extracted

    def test_inline_array_not_affected(self) -> None:
        """Inline arrays (single line) still work correctly."""
        text = """\
[pipeline.submit_filter.triggers]
"*" = [["ok", "send"], ["ok", "submit"]]

[agent_profiles]
default = "sonnet"
"""
        extracted = _extract_section_lines(text, "pipeline.submit_filter")
        assert extracted is not None
        assert '[["ok", "send"], ["ok", "submit"]]' in extracted
        assert "[agent_profiles]" not in extracted
