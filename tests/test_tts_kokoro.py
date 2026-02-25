"""Tests for Kokoro TTS engine."""

from __future__ import annotations

from unittest.mock import patch

def test_kokoro_tts_get_name():
    """KokoroTTS.get_name() returns 'kokoro'."""
    from dictare.tts.kokoro import KokoroTTS

    engine = KokoroTTS()
    assert engine.get_name() == "kokoro"

def test_kokoro_tts_unavailable_when_not_installed():
    """KokoroTTS.is_available() returns False when kokoro-onnx is missing."""
    from dictare.tts.kokoro import KokoroTTS

    engine = KokoroTTS()
    with patch.dict("sys.modules", {"kokoro_onnx": None}):
        engine._available = None  # reset cache
        assert engine.is_available() is False

def test_kokoro_tts_speak_returns_false_when_unavailable():
    """KokoroTTS.speak() returns False when not available."""
    from dictare.tts.kokoro import KokoroTTS

    engine = KokoroTTS()
    engine._available = False
    assert engine.speak("test") is False

def test_kokoro_tts_default_params():
    """KokoroTTS stores default parameters correctly."""
    from dictare.tts.kokoro import KokoroTTS

    engine = KokoroTTS()
    assert engine.language == "en"
    assert engine.speed == 1.0
    assert engine.voice == "af_heart"

def test_kokoro_tts_custom_params():
    """KokoroTTS stores custom parameters correctly."""
    from dictare.tts.kokoro import KokoroTTS

    engine = KokoroTTS(language="it", speed=1.5, voice="if_sara")
    assert engine.language == "it"
    assert engine.speed == 1.5
    assert engine.voice == "if_sara"

def test_kokoro_resolve_lang():
    """_resolve_lang maps dictare codes to kokoro codes."""
    from dictare.tts.kokoro import KokoroTTS

    assert KokoroTTS._resolve_lang("en") == "en-us"
    assert KokoroTTS._resolve_lang("it") == "it"
    assert KokoroTTS._resolve_lang("fr") == "fr-fr"

    # Unknown language falls back to en-us
    assert KokoroTTS._resolve_lang("xx") == "en-us"

def test_kokoro_resolve_voice():
    """_resolve_voice picks appropriate default per language."""
    from dictare.tts.kokoro import KokoroTTS

    # Explicit voice takes priority
    assert KokoroTTS._resolve_voice("en", "bf_emma") == "bf_emma"

    # Empty voice → language default
    assert KokoroTTS._resolve_voice("it", "") == "if_sara"

    # Unknown language → af_heart fallback
    assert KokoroTTS._resolve_voice("xx", "") == "af_heart"
