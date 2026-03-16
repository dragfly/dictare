"""Additional tests for TOML section management (dictare.core.toml_sections)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dictare.core.toml_sections import (
    _SECTION_HEADERS,
    SUPPORTED_SECTIONS,
    _extract_section_lines,
    _strip_section_lines,
    _write_section_raw,
    apply_section,
    shortcuts_to_toml,
)

# ---------------------------------------------------------------------------
# SUPPORTED_SECTIONS
# ---------------------------------------------------------------------------

class TestSupportedSections:
    def test_all_have_headers(self) -> None:
        for section in SUPPORTED_SECTIONS:
            assert section in _SECTION_HEADERS

    def test_expected_sections_present(self) -> None:
        expected = {
            "agent_profiles",
            "keyboard.shortcuts",
            "audio.advanced",
            "audio.sounds",
            "stt.advanced",
            "pipeline.mute_filter",
            "pipeline.submit_filter",
            "pipeline.agent_filter",
        }
        assert SUPPORTED_SECTIONS == expected


# ---------------------------------------------------------------------------
# shortcuts_to_toml
# ---------------------------------------------------------------------------

class TestShortcutsToToml:
    def test_empty_list(self) -> None:
        result = shortcuts_to_toml([])
        assert "No keyboard shortcuts" in result

    def test_single_shortcut(self) -> None:
        result = shortcuts_to_toml([{"keys": "ctrl+l", "command": "toggle-listening"}])
        assert "[[keyboard.shortcuts]]" in result
        assert 'keys = "ctrl+l"' in result
        assert 'command = "toggle-listening"' in result

    def test_multiple_shortcuts(self) -> None:
        shortcuts = [
            {"keys": "ctrl+l", "command": "toggle-listening"},
            {"keys": "ctrl+n", "command": "next-agent"},
        ]
        result = shortcuts_to_toml(shortcuts)
        assert result.count("[[keyboard.shortcuts]]") == 2


# ---------------------------------------------------------------------------
# _extract_section_lines
# ---------------------------------------------------------------------------

class TestExtractSectionLines:
    def test_absent_section_returns_none(self) -> None:
        text = "[stt]\nmodel = \"base\"\n"
        assert _extract_section_lines(text, "agent_profiles") is None

    def test_unknown_section_returns_none(self) -> None:
        assert _extract_section_lines("[stt]\n", "nonexistent") is None

    def test_extracts_simple_section(self) -> None:
        text = """\
[stt]
model = "base"

[audio.advanced]
sample_rate = 16000

[tts]
engine = "say"
"""
        result = _extract_section_lines(text, "audio.advanced")
        assert result is not None
        assert "[audio.advanced]" in result
        assert "sample_rate = 16000" in result
        assert "[stt]" not in result
        assert "[tts]" not in result

    def test_extracts_keyboard_shortcuts(self) -> None:
        text = """\
[stt]
model = "base"

[[keyboard.shortcuts]]
keys = "ctrl+l"
command = "toggle-listening"

[[keyboard.shortcuts]]
keys = "ctrl+n"
command = "next-agent"

[tts]
engine = "say"
"""
        result = _extract_section_lines(text, "keyboard.shortcuts")
        assert result is not None
        assert result.count("[[keyboard.shortcuts]]") == 2
        assert "ctrl+l" in result
        assert "ctrl+n" in result
        assert "[stt]" not in result

    def test_comments_before_owned_after_nonowned_not_extracted(self) -> None:
        """Comments between a non-owned section and an owned header belong
        to the non-owned section (buffer is discarded when inside non-owned)."""
        text = """\
[stt]
model = "base"

# Pipeline filter config
[pipeline.submit_filter]
enabled = true
"""
        result = _extract_section_lines(text, "pipeline.submit_filter")
        assert result is not None
        assert "[pipeline.submit_filter]" in result
        # Comment is inside non-owned [stt] section, so NOT extracted
        assert "# Pipeline filter config" not in result

    def test_comments_before_owned_at_top_level_extracted(self) -> None:
        """Comments at top level (not inside any section) before an owned header
        are flushed as belonging to the owned section."""
        text = """\
# Pipeline filter config
[pipeline.submit_filter]
enabled = true
"""
        result = _extract_section_lines(text, "pipeline.submit_filter")
        assert result is not None
        assert "# Pipeline filter config" in result
        assert "[pipeline.submit_filter]" in result

    def test_comments_after_nonowned_header_not_extracted(self) -> None:
        text = """\
[stt]
# This comment belongs to stt
model = "base"

[audio.advanced]
sample_rate = 16000
"""
        result = _extract_section_lines(text, "audio.advanced")
        assert result is not None
        assert "# This comment belongs to stt" not in result

    def test_sounds_with_subkeys(self) -> None:
        text = """\
[audio.sounds.start]
enabled = true
volume = 0.5

[audio.sounds.stop]
enabled = false

[stt]
model = "base"
"""
        result = _extract_section_lines(text, "audio.sounds")
        assert result is not None
        assert "[audio.sounds.start]" in result
        assert "[audio.sounds.stop]" in result
        assert "volume = 0.5" in result
        assert "[stt]" not in result


# ---------------------------------------------------------------------------
# _strip_section_lines
# ---------------------------------------------------------------------------

class TestStripSectionLinesExtra:
    def test_strips_keyboard_shortcuts(self) -> None:
        text = """\
[stt]
model = "base"

[[keyboard.shortcuts]]
keys = "ctrl+l"
command = "toggle-listening"

[tts]
engine = "say"
"""
        stripped = _strip_section_lines(text, "keyboard.shortcuts")
        assert "[[keyboard.shortcuts]]" not in stripped
        assert "ctrl+l" not in stripped
        assert "[stt]" in stripped
        assert "[tts]" in stripped

    def test_strips_pipeline_filter(self) -> None:
        text = """\
[pipeline.submit_filter]
enabled = true

[pipeline.submit_filter.triggers]
"*" = [["ok", "send"]]

[stt]
model = "base"
"""
        stripped = _strip_section_lines(text, "pipeline.submit_filter")
        assert "[pipeline.submit_filter" not in stripped
        assert "[stt]" in stripped

    def test_strip_preserves_trailing_comments(self) -> None:
        text = """\
[stt]
model = "base"

# End of file comment
"""
        stripped = _strip_section_lines(text, "agent_profiles")
        assert "# End of file comment" in stripped


# ---------------------------------------------------------------------------
# _write_section_raw
# ---------------------------------------------------------------------------

class TestWriteSectionRaw:
    def test_writes_to_new_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        _write_section_raw("agent_profiles", "[agent_profiles]\ndefault = \"sonnet\"\n", config_path)
        content = config_path.read_text()
        assert "[agent_profiles]" in content
        assert 'default = "sonnet"' in content

    def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('[stt]\nmodel = "base"\n')
        _write_section_raw("audio.advanced", "[audio.advanced]\nsample_rate = 16000\n", config_path)
        content = config_path.read_text()
        assert "[stt]" in content
        assert "[audio.advanced]" in content

    def test_replaces_existing_section(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[stt]\nmodel = "base"\n\n[audio.advanced]\nsample_rate = 16000\n'
        )
        _write_section_raw("audio.advanced", "[audio.advanced]\nsample_rate = 48000\n", config_path)
        content = config_path.read_text()
        assert "48000" in content
        assert "16000" not in content

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        config_path = tmp_path / "deep" / "nested" / "config.toml"
        _write_section_raw("stt.advanced", "[stt.advanced]\nbeam_size = 3\n", config_path)
        assert config_path.exists()


# ---------------------------------------------------------------------------
# apply_section validation
# ---------------------------------------------------------------------------

class TestApplySectionValidation:
    def test_unknown_section_raises_key_error(self, tmp_path: Path) -> None:
        with pytest.raises(KeyError):
            apply_section("nonexistent", "content", tmp_path / "config.toml")

    def test_invalid_toml_raises_value_error(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("")
        with pytest.raises(ValueError, match="TOML"):
            apply_section("audio.advanced", "[audio.advanced\n", config_path)

    def test_valid_audio_advanced(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("")
        apply_section("audio.advanced", "[audio.advanced]\nsample_rate = 16000\n", config_path)
        content = config_path.read_text()
        assert "sample_rate = 16000" in content

    def test_valid_keyboard_shortcuts(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("")
        content = '[[keyboard.shortcuts]]\nkeys = "ctrl+l"\ncommand = "toggle-listening"\n'
        apply_section("keyboard.shortcuts", content, config_path)
        assert "ctrl+l" in config_path.read_text()

    def test_agent_profiles_default_must_be_string(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("")
        with pytest.raises(ValueError, match="string"):
            apply_section("agent_profiles", "[agent_profiles]\ndefault = 42\n", config_path)

    def test_valid_mute_filter(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("")
        apply_section(
            "pipeline.mute_filter",
            "[pipeline.mute_filter]\nenabled = true\n",
            config_path,
        )

    def test_valid_submit_filter(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("")
        apply_section(
            "pipeline.submit_filter",
            "[pipeline.submit_filter]\nenabled = true\n",
            config_path,
        )

    def test_valid_agent_filter(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text("")
        apply_section(
            "pipeline.agent_filter",
            "[pipeline.agent_filter]\nenabled = false\n",
            config_path,
        )


# ---------------------------------------------------------------------------
# Section headers are valid TOML
# ---------------------------------------------------------------------------

class TestSectionHeaders:
    @pytest.mark.parametrize("section", sorted(SUPPORTED_SECTIONS))
    def test_header_is_parseable_toml(self, section: str) -> None:
        import tomlkit
        header = _SECTION_HEADERS[section]
        # Should parse without error (comments are valid TOML)
        tomlkit.parse(header)
