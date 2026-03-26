"""Extra tests for agent multiplexer — claim key, strip helpers, session summary."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from dictare.agent.mux import (
    _CTRL_BACKSLASH,
    _CTRL_BACKSLASH_SEQS,
    _parse_claim_key,
    _print_session_summary,
    _report_focus,
    _strip_claim_key,
    _strip_ctrl_backslash,
)

# ---------------------------------------------------------------------------
# _parse_claim_key
# ---------------------------------------------------------------------------

class TestParseClaimKey:
    """Test claim key parsing."""

    def test_ctrl_backslash(self) -> None:
        raw, csi = _parse_claim_key("ctrl+\\")
        assert raw == _CTRL_BACKSLASH
        assert csi == _CTRL_BACKSLASH_SEQS

    def test_ctrl_close_bracket(self) -> None:
        raw, seqs = _parse_claim_key("ctrl+]")
        assert raw == bytes([ord("]") & 0x1F])
        assert f"\x1b[{ord(']')};5u".encode() in seqs

    def test_case_insensitive(self) -> None:
        raw1, csi1 = _parse_claim_key("CTRL+A")
        raw2, csi2 = _parse_claim_key("ctrl+a")
        assert raw1 == raw2
        assert csi1 == csi2

    def test_invalid_format_no_ctrl(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            _parse_claim_key("alt+x")

    def test_invalid_format_too_short(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            _parse_claim_key("ctrl")

    def test_invalid_multi_char(self) -> None:
        with pytest.raises(ValueError, match="single character"):
            _parse_claim_key("ctrl+ab")


# ---------------------------------------------------------------------------
# _strip_claim_key
# ---------------------------------------------------------------------------

class TestStripClaimKey:
    """Test _strip_claim_key."""

    def test_no_claim_key(self) -> None:
        data = b"hello"
        cleaned, found = _strip_claim_key(data, _CTRL_BACKSLASH, _CTRL_BACKSLASH_SEQS)
        assert cleaned == b"hello"
        assert found is False

    def test_raw_claim_key(self) -> None:
        data = b"abc" + _CTRL_BACKSLASH + b"def"
        cleaned, found = _strip_claim_key(data, _CTRL_BACKSLASH, _CTRL_BACKSLASH_SEQS)
        assert cleaned == b"abcdef"
        assert found is True

    def test_csi_u_claim_key(self) -> None:
        data = b"abc" + _CTRL_BACKSLASH_SEQS[0] + b"def"
        cleaned, found = _strip_claim_key(data, _CTRL_BACKSLASH, _CTRL_BACKSLASH_SEQS)
        assert cleaned == b"abcdef"
        assert found is True

    def test_modify_other_keys_claim_key(self) -> None:
        data = b"abc" + _CTRL_BACKSLASH_SEQS[1] + b"def"
        cleaned, found = _strip_claim_key(data, _CTRL_BACKSLASH, _CTRL_BACKSLASH_SEQS)
        assert cleaned == b"abcdef"
        assert found is True

    def test_both_variants(self) -> None:
        data = _CTRL_BACKSLASH + _CTRL_BACKSLASH_SEQS[0]
        cleaned, found = _strip_claim_key(data, _CTRL_BACKSLASH, _CTRL_BACKSLASH_SEQS)
        assert cleaned == b""
        assert found is True


# ---------------------------------------------------------------------------
# _strip_ctrl_backslash (backward compat)
# ---------------------------------------------------------------------------

class TestStripCtrlBackslash:
    """Test backward-compatible _strip_ctrl_backslash wrapper."""

    def test_no_key(self) -> None:
        cleaned, found = _strip_ctrl_backslash(b"abc")
        assert cleaned == b"abc"
        assert found is False

    def test_with_key(self) -> None:
        cleaned, found = _strip_ctrl_backslash(b"a\x1cb")
        assert cleaned == b"ab"
        assert found is True


# ---------------------------------------------------------------------------
# _report_focus
# ---------------------------------------------------------------------------

class TestReportFocus:
    """Test _report_focus fire-and-forget."""

    def test_report_focus_does_not_block(self) -> None:
        """_report_focus fires a thread and returns immediately."""
        with patch("urllib.request.urlopen"):
            _report_focus("claude", "http://localhost:8770/openvip", True)
        # Should return immediately without error

    def test_report_focus_false(self) -> None:
        with patch("urllib.request.urlopen"):
            _report_focus("claude", "http://localhost:8770/openvip", False)


# ---------------------------------------------------------------------------
# _print_session_summary
# ---------------------------------------------------------------------------

class TestPrintSessionSummary:
    """Test _print_session_summary."""

    def test_no_transcriptions_prints_nothing(self, capsys) -> None:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps({
            "platform": {"stats": {"transcriptions": 0}},
        }).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            _print_session_summary("http://localhost:8770/openvip")

        captured = capsys.readouterr()
        assert captured.err == ""  # nothing printed

    def test_with_transcriptions(self, capsys) -> None:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps({
            "platform": {
                "stats": {
                    "transcriptions": 5,
                    "words": 50,
                    "chars": 250,
                    "audio_seconds": 15.0,
                    "transcription_seconds": 3.0,
                    "injection_seconds": 0.5,
                },
            },
        }).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            _print_session_summary("http://localhost:8770/openvip")

        captured = capsys.readouterr()
        assert "Transcriptions" in captured.err
        assert "Words" in captured.err

    def test_connection_error_silent(self) -> None:
        """Connection error is silently ignored."""
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError):
            _print_session_summary("http://localhost:8770/openvip")
        # Should not raise


# ---------------------------------------------------------------------------
# Custom claim key parsing
# ---------------------------------------------------------------------------

class TestCustomClaimKeys:
    """Test _parse_claim_key with various keys."""

    def test_ctrl_a(self) -> None:
        raw, csi = _parse_claim_key("ctrl+a")
        assert raw == b"\x01"
        assert b"\x1b[97;5u" in csi

    def test_ctrl_z(self) -> None:
        raw, csi = _parse_claim_key("ctrl+z")
        assert raw == b"\x1a"
        assert b"\x1b[122;5u" in csi

    def test_ctrl_close_bracket_raw(self) -> None:
        raw, _ = _parse_claim_key("ctrl+]")
        assert raw == b"\x1d"  # ord(']') & 0x1F = 93 & 31 = 29 = 0x1d
