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

def test_kokoro_lang_from_voice():
    """_lang_from_voice infers language from voice name prefix."""
    from dictare.tts.kokoro import KokoroTTS

    assert KokoroTTS._lang_from_voice("if_sara") == "it"
    assert KokoroTTS._lang_from_voice("im_nicola") == "it"
    assert KokoroTTS._lang_from_voice("af_heart") == "en"
    assert KokoroTTS._lang_from_voice("bf_emma") == "en-gb"
    assert KokoroTTS._lang_from_voice("ef_dora") == "es"
    assert KokoroTTS._lang_from_voice("ff_siwis") == "fr"
    assert KokoroTTS._lang_from_voice("jf_alpha") == "ja"
    assert KokoroTTS._lang_from_voice("zf_xiaobei") == "zh"
    assert KokoroTTS._lang_from_voice("unknown") is None

def test_kokoro_resolve_params_voice_sets_language():
    """Voice prefix determines language, overriding default 'en'."""
    from dictare.tts.kokoro import KokoroTTS

    # Instance with empty voice — matches real worker startup (--voice "")
    tts = KokoroTTS(language="en", voice="")

    # No explicit -l → voice prefix determines language
    lang, voice = tts._resolve_params(voice="if_sara", language=None)
    assert lang == "it"
    assert voice == "if_sara"

    # Explicit -l overrides voice inference (-v if_sara -l fr → French phonetics)
    lang, voice = tts._resolve_params(voice="if_sara", language="fr")
    assert lang == "fr-fr"

    # Explicit -l en → English phonetics (user knows what they want)
    lang, voice = tts._resolve_params(voice="if_sara", language="en")
    assert lang == "en-us"

    # English voice → English phonetics
    lang, voice = tts._resolve_params(voice="af_heart", language=None)
    assert lang == "en-us"

    # No explicit voice → language determines phonetics and default voice
    lang, voice = tts._resolve_params(voice=None, language="it")
    assert lang == "it"
    assert voice == "if_sara"  # language-appropriate default
