"""Tests for check_all_tts_engines() and check_all_stt_engines()."""

from __future__ import annotations

from unittest.mock import patch


class TestCheckAllTTSEngines:
    """Test check_all_tts_engines()."""

    def test_returns_five_engines(self) -> None:
        """All 5 TTS engines are always reported."""
        from dictare.utils.platform import check_all_tts_engines

        results = check_all_tts_engines()
        names = [r["name"] for r in results]
        assert names == ["say", "espeak", "piper", "coqui", "outetts"]

    def test_all_dicts_have_required_keys(self) -> None:
        """Every result dict has the expected keys."""
        from dictare.utils.platform import check_all_tts_engines

        required = {"name", "available", "description", "platform_ok", "install_hint", "configured"}
        for eng in check_all_tts_engines():
            assert required <= set(eng.keys()), f"Missing keys in {eng['name']}"

    def test_configured_flag(self) -> None:
        """Passing configured_engine marks the right engine."""
        from dictare.utils.platform import check_all_tts_engines

        results = check_all_tts_engines("piper")
        by_name = {r["name"]: r for r in results}
        assert by_name["piper"]["configured"] is True
        assert by_name["say"]["configured"] is False
        assert by_name["espeak"]["configured"] is False

    def test_say_platform_ok_only_on_macos(self) -> None:
        """say.platform_ok is True only on macOS."""
        import sys

        from dictare.utils.platform import check_all_tts_engines

        results = check_all_tts_engines()
        say = next(r for r in results if r["name"] == "say")
        assert say["platform_ok"] == (sys.platform == "darwin")

    def test_espeak_missing_when_not_in_path(self) -> None:
        """espeak shows as unavailable when not in PATH and no brew fallback."""
        from dictare.utils.platform import check_all_tts_engines

        with (
            patch("dictare.utils.platform.shutil.which", return_value=None),
            patch("dictare.utils.platform.Path.exists", return_value=False),
        ):
            results = check_all_tts_engines()
            espeak = next(r for r in results if r["name"] == "espeak")
            assert espeak["available"] is False
            assert espeak["install_hint"] != ""

    def test_espeak_available_when_espeak_ng_found(self) -> None:
        """espeak is available when espeak-ng is in PATH."""
        from dictare.utils.platform import check_all_tts_engines

        def mock_which(cmd: str) -> str | None:
            if cmd == "espeak-ng":
                return "/usr/bin/espeak-ng"
            return None

        with patch("dictare.utils.platform.shutil.which", side_effect=mock_which):
            results = check_all_tts_engines()
            espeak = next(r for r in results if r["name"] == "espeak")
            assert espeak["available"] is True

    def test_piper_found_in_python_bin(self) -> None:
        """piper found via _find_in_python_bin fallback."""
        from dictare.utils.platform import check_all_tts_engines

        with (
            patch("dictare.utils.platform.shutil.which", return_value=None),
            patch("dictare.utils.platform._find_in_python_bin", side_effect=lambda n: n == "piper"),
        ):
            results = check_all_tts_engines()
            piper = next(r for r in results if r["name"] == "piper")
            assert piper["available"] is True

    def test_outetts_unavailable_on_non_apple_silicon(self) -> None:
        """outetts shows as unavailable on non-Apple Silicon."""
        from dictare.utils.platform import check_all_tts_engines

        with patch("dictare.utils.hardware.is_apple_silicon", return_value=False):
            results = check_all_tts_engines()
            outetts = next(r for r in results if r["name"] == "outetts")
            assert outetts["available"] is False
            assert outetts["platform_ok"] is False


class TestCheckAllSTTEngines:
    """Test check_all_stt_engines()."""

    def test_returns_three_engines(self) -> None:
        """All 3 STT backends are always reported."""
        from dictare.utils.platform import check_all_stt_engines

        results = check_all_stt_engines()
        names = [r["name"] for r in results]
        assert names == ["parakeet", "mlx-whisper", "faster-whisper"]

    def test_all_dicts_have_required_keys(self) -> None:
        """Every result dict has the expected keys."""
        from dictare.utils.platform import check_all_stt_engines

        required = {"name", "available", "description", "platform_ok", "install_hint", "configured"}
        for eng in check_all_stt_engines():
            assert required <= set(eng.keys()), f"Missing keys in {eng['name']}"

    def test_configured_parakeet(self) -> None:
        """Parakeet shows as configured when model starts with 'parakeet'."""
        from dictare.utils.platform import check_all_stt_engines

        results = check_all_stt_engines("parakeet-v3")
        parakeet = next(r for r in results if r["name"] == "parakeet")
        assert parakeet["configured"] is True

    def test_mlx_whisper_unavailable_on_non_apple_silicon(self) -> None:
        """mlx-whisper shows as unavailable on non-Apple Silicon."""
        from dictare.utils.platform import check_all_stt_engines

        with patch("dictare.utils.hardware.is_apple_silicon", return_value=False):
            results = check_all_stt_engines()
            mlx = next(r for r in results if r["name"] == "mlx-whisper")
            assert mlx["available"] is False
            assert mlx["platform_ok"] is False
