"""Tests for TTS CLI commands (dictare.cli.speak)."""

from __future__ import annotations

from dictare.cli.speak import (
    _KOKORO_GENDER,
    _KOKORO_LANG_PREFIX,
    _print_voices,
    _send_stop,
)

# ---------------------------------------------------------------------------
# Kokoro voice constants
# ---------------------------------------------------------------------------

class TestKokoroConstants:
    def test_lang_prefix_keys(self) -> None:
        expected = {"a", "b", "e", "f", "h", "i", "j", "p", "z"}
        assert set(_KOKORO_LANG_PREFIX.keys()) == expected

    def test_lang_prefix_values(self) -> None:
        assert _KOKORO_LANG_PREFIX["a"] == "EN-US"
        assert _KOKORO_LANG_PREFIX["i"] == "IT"
        assert _KOKORO_LANG_PREFIX["j"] == "JA"

    def test_gender_keys(self) -> None:
        assert set(_KOKORO_GENDER.keys()) == {"f", "m"}
        assert _KOKORO_GENDER["f"] == "F"
        assert _KOKORO_GENDER["m"] == "M"


# ---------------------------------------------------------------------------
# _print_voices
# ---------------------------------------------------------------------------

class TestPrintVoices:
    def test_prints_kokoro_voices(self, capsys) -> None:
        from unittest.mock import patch

        # _print_voices uses console.print (rich), so mock it
        with patch("dictare.cli.speak.console") as mock_console:
            _print_voices("kokoro", ["af_sara", "im_nicola", "simple_voice"])
            # Should have been called for header + each voice + footer
            assert mock_console.print.call_count >= 4

    def test_empty_voices_list(self) -> None:
        from unittest.mock import patch

        with patch("dictare.cli.speak.console") as mock_console:
            _print_voices("kokoro", [])
            # Header (with count 0) + footer
            assert mock_console.print.call_count >= 2


# ---------------------------------------------------------------------------
# _send_stop
# ---------------------------------------------------------------------------

class TestSendStop:
    def test_send_stop_best_effort(self) -> None:
        """_send_stop should not raise even on errors."""
        from types import SimpleNamespace
        from unittest.mock import patch

        config = SimpleNamespace(
            server=SimpleNamespace(host="127.0.0.1", port=9999)
        )
        # Connection error should be swallowed
        with patch("openvip.Client", side_effect=ConnectionRefusedError):
            _send_stop(config)  # should not raise

    def test_send_stop_calls_client(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch

        config = SimpleNamespace(
            server=SimpleNamespace(host="127.0.0.1", port=9999)
        )
        mock_client = MagicMock()
        with patch("openvip.Client", return_value=mock_client):
            _send_stop(config)

        mock_client.stop_speech.assert_called_once()
