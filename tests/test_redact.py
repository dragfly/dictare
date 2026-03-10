"""Tests for terminal output redaction."""

from __future__ import annotations

import tempfile
from pathlib import Path

from dictare.config import Config

class TestRedactConfig:
    """Test redact field in Config."""

    def test_redact_default_empty(self) -> None:
        config = Config()
        assert config.redact == []

    def test_redact_parses_pairs(self) -> None:
        config = Config(redact=[["secret", "***"], ["password", "****"]])
        assert len(config.redact) == 2
        assert config.redact[0] == ["secret", "***"]
        assert config.redact[1] == ["password", "****"]

    def test_redact_from_toml(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('redact = [["myname", "REDACTED"], ["/Users/me", "/Users/***"]]\n')

        from dictare.config import load_config

        config = load_config(toml_file)
        assert config.redact == [["myname", "REDACTED"], ["/Users/me", "/Users/***"]]

class TestRedactRules:
    """Test redaction logic applied to output bytes."""

    @staticmethod
    def _apply_redact(data: bytes, rules: list[list[str]]) -> bytes:
        """Replicate the redaction logic from mux.py."""
        redact_rules = []
        for rule in rules:
            if len(rule) == 2:
                redact_rules.append((rule[0].encode(), rule[1].encode()))
        for find, replace in redact_rules:
            data = data.replace(find, replace)
        return data

    def test_single_rule(self) -> None:
        data = b"Hello alice, welcome"
        result = self._apply_redact(data, [["alice", "dragfly"]])
        assert result == b"Hello dragfly, welcome"

    def test_multiple_rules(self) -> None:
        data = b"/Users/alice/repos/project"
        rules = [["alice", "dragfly"], ["/Users/dragfly", "/home/user"]]
        result = self._apply_redact(data, rules)
        assert result == b"/home/user/repos/project"

    def test_no_rules(self) -> None:
        data = b"unchanged output"
        result = self._apply_redact(data, [])
        assert result == b"unchanged output"

    def test_no_match(self) -> None:
        data = b"nothing to redact here"
        result = self._apply_redact(data, [["secret", "***"]])
        assert result == b"nothing to redact here"

    def test_malformed_rule_ignored(self) -> None:
        data = b"keep this"
        result = self._apply_redact(data, [["only_one_element"], ["good", "ok"]])
        assert result == b"keep this"

    def test_multiple_occurrences(self) -> None:
        data = b"name is alice and alice says hi"
        result = self._apply_redact(data, [["alice", "***"]])
        assert result == b"name is *** and *** says hi"
