"""Tests for TTS audio caching across all engines."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# cache module tests
# ---------------------------------------------------------------------------


class TestCacheModule:
    """Tests for dictare.tts.cache functions."""

    def test_cache_key_deterministic(self):
        """Same inputs produce the same cache key."""
        from dictare.tts.cache import cache_key

        k1 = cache_key("kokoro", "hello", "en-us", "af_heart")
        k2 = cache_key("kokoro", "hello", "en-us", "af_heart")
        assert k1 == k2

    def test_cache_key_varies_by_engine(self):
        """Different engines produce different keys for same text."""
        from dictare.tts.cache import cache_key

        k1 = cache_key("kokoro", "hello", "en", "voice")
        k2 = cache_key("piper", "hello", "en", "voice")
        assert k1 != k2

    def test_cache_key_varies_by_text(self):
        """Different text produces different keys."""
        from dictare.tts.cache import cache_key

        k1 = cache_key("kokoro", "hello", "en", "voice")
        k2 = cache_key("kokoro", "world", "en", "voice")
        assert k1 != k2

    def test_cache_key_varies_by_voice(self):
        """Different voice produces different keys."""
        from dictare.tts.cache import cache_key

        k1 = cache_key("kokoro", "hello", "en", "voice_a")
        k2 = cache_key("kokoro", "hello", "en", "voice_b")
        assert k1 != k2

    def test_cache_path_uses_audio_extension(self):
        """Cached files use .audio extension (format-agnostic)."""
        from dictare.tts.cache import cache_path

        p = cache_path("abc123")
        assert p.suffix == ".audio"
        assert p.name == "abc123.audio"

    def test_cache_hit_miss(self, tmp_path: Path):
        """cache_hit returns None when file doesn't exist."""
        from dictare.tts.cache import cache_hit

        with patch("dictare.tts.cache._CACHE_DIR", tmp_path):
            assert cache_hit("nonexistent") is None

    def test_cache_hit_returns_path(self, tmp_path: Path):
        """cache_hit returns path and touches mtime when file exists."""
        from dictare.tts.cache import cache_hit

        with patch("dictare.tts.cache._CACHE_DIR", tmp_path):
            cached = tmp_path / "abc123.audio"
            cached.write_bytes(b"fake audio")
            result = cache_hit("abc123")
            assert result == cached

    def test_cache_save_copies_file(self, tmp_path: Path):
        """cache_save copies source file into cache dir."""
        from dictare.tts.cache import cache_save

        cache_dir = tmp_path / "cache"
        src = tmp_path / "source.wav"
        src.write_bytes(b"audio data")

        with patch("dictare.tts.cache._CACHE_DIR", cache_dir):
            result = cache_save("mykey", src)
            assert result.exists()
            assert result.name == "mykey.audio"
            assert result.read_bytes() == b"audio data"

    def test_cache_evict_removes_oldest(self, tmp_path: Path):
        """cache_evict removes oldest files when over limit."""
        import os
        import time

        from dictare.tts.cache import cache_evict

        with patch("dictare.tts.cache._CACHE_DIR", tmp_path), \
             patch("dictare.tts.cache._MAX_CACHED", 2):
            # Create 4 files with different mtimes
            for i in range(4):
                f = tmp_path / f"file{i}.audio"
                f.write_bytes(b"data")
                os.utime(f, (time.time() + i, time.time() + i))

            cache_evict()

            remaining = sorted(f.name for f in tmp_path.glob("*.audio"))
            assert len(remaining) == 2
            # Newest 2 should remain
            assert remaining == ["file2.audio", "file3.audio"]


# ---------------------------------------------------------------------------
# Engine cache integration tests
# ---------------------------------------------------------------------------


class TestPiperCache:
    """Piper TTS uses cache correctly."""

    def test_check_cache_returns_none_on_miss(self, tmp_path: Path):
        """check_cache returns None when not cached."""
        from dictare.tts.piper import PiperTTS

        engine = PiperTTS(language="en", voice="en_US-lessac-medium")
        with patch("dictare.tts.cache._CACHE_DIR", tmp_path):
            assert engine.check_cache("hello") is None

    def test_check_cache_returns_path_on_hit(self, tmp_path: Path):
        """check_cache returns path when cached."""
        from dictare.tts.cache import cache_key
        from dictare.tts.piper import PiperTTS

        engine = PiperTTS(language="en", voice="en_US-lessac-medium")
        key = cache_key("piper", "hello", "en", "en_US-lessac-medium")
        cached = tmp_path / f"{key}.audio"
        cached.write_bytes(b"audio")

        with patch("dictare.tts.cache._CACHE_DIR", tmp_path):
            result = engine.check_cache("hello")
            assert result == cached

    def test_speak_plays_from_cache(self, tmp_path: Path):
        """speak() plays from cache on hit without generating."""
        from dictare.tts.cache import cache_key
        from dictare.tts.piper import PiperTTS

        engine = PiperTTS(language="en", voice="en_US-lessac-medium")
        engine._piper_cmd = "/usr/bin/piper"
        key = cache_key("piper", "hello", "en", "en_US-lessac-medium")
        cached = tmp_path / f"{key}.audio"
        cached.write_bytes(b"audio")

        with patch("dictare.tts.cache._CACHE_DIR", tmp_path), \
             patch("dictare.tts.piper.play_audio_native") as mock_play, \
             patch("subprocess.run") as mock_run:
            result = engine.speak("hello")
            assert result is True
            mock_play.assert_called_once()
            mock_run.assert_not_called()  # No generation on cache hit


class TestEspeakCache:
    """espeak TTS uses cache correctly."""

    def test_check_cache_returns_none_on_miss(self, tmp_path: Path):
        """check_cache returns None when not cached."""
        from dictare.tts.espeak import EspeakTTS

        engine = EspeakTTS(language="en", speed=160)
        with patch("dictare.tts.cache._CACHE_DIR", tmp_path):
            assert engine.check_cache("hello") is None

    def test_cache_key_includes_speed(self):
        """espeak cache key includes speed (not just voice)."""
        from dictare.tts.espeak import EspeakTTS

        e1 = EspeakTTS(language="en", speed=160)
        e2 = EspeakTTS(language="en", speed=200)
        assert e1._cache_key("hello") != e2._cache_key("hello")


class TestSayCache:
    """macOS say TTS uses cache correctly."""

    def test_check_cache_returns_none_on_miss(self, tmp_path: Path):
        """check_cache returns None when not cached."""
        from dictare.tts.say import SayTTS

        engine = SayTTS(language="en", speed=175)
        with patch("dictare.tts.cache._CACHE_DIR", tmp_path):
            assert engine.check_cache("hello") is None

    def test_cache_key_includes_speed(self):
        """say cache key includes speed."""
        from dictare.tts.say import SayTTS

        e1 = SayTTS(language="en", speed=175)
        e2 = SayTTS(language="en", speed=200)
        assert e1._cache_key("hello") != e2._cache_key("hello")

    def test_speak_uses_aiff_temp(self, tmp_path: Path):
        """say generates .aiff temp file (not .wav)."""
        from dictare.tts.say import SayTTS

        engine = SayTTS(language="en", speed=175)

        with patch("dictare.tts.cache._CACHE_DIR", tmp_path), \
             patch("dictare.tts.say.play_audio_native"), \
             patch("subprocess.run") as mock_run, \
             patch("shutil.which", return_value="/usr/bin/say"), \
             patch("sys.platform", "darwin"):
            mock_run.return_value = MagicMock(returncode=0)

            # Mock tempfile to capture the suffix
            import tempfile as tf
            orig = tf.NamedTemporaryFile
            suffixes_used = []

            def capture_suffix(*args, **kwargs):
                suffixes_used.append(kwargs.get("suffix", ""))
                return orig(*args, **kwargs)

            with patch("dictare.tts.say.tempfile.NamedTemporaryFile", side_effect=capture_suffix):
                engine.speak("test")

            assert ".aiff" in suffixes_used


class TestCoquiCache:
    """Coqui TTS uses cache correctly."""

    def test_check_cache_returns_none_on_miss(self, tmp_path: Path):
        """check_cache returns None when not cached."""
        from dictare.tts.coqui import CoquiTTS

        engine = CoquiTTS(language="en")
        with patch("dictare.tts.cache._CACHE_DIR", tmp_path):
            assert engine.check_cache("hello") is None


class TestOuteTTSCache:
    """OuteTTS uses cache correctly."""

    def test_check_cache_returns_none_on_miss(self, tmp_path: Path):
        """check_cache returns None when not cached."""
        from dictare.tts.outetts import OuteTTS

        engine = OuteTTS(language="en")
        with patch("dictare.tts.cache._CACHE_DIR", tmp_path):
            assert engine.check_cache("hello") is None

    def test_cache_key_includes_model_size(self):
        """OuteTTS cache key includes model size."""
        from dictare.tts.outetts import OuteTTS

        e1 = OuteTTS(language="en", model_size="small")
        e2 = OuteTTS(language="en", model_size="large")
        assert e1._cache_key("hello") != e2._cache_key("hello")


class TestKokoroCache:
    """Kokoro TTS cache key uses resolved params."""

    def test_cache_key_uses_resolved_lang(self):
        """Cache key uses resolved language (en-us, not en)."""
        from dictare.tts.kokoro import KokoroTTS

        engine = KokoroTTS(language="en", voice="af_heart")
        key, lang, voice = engine._get_cache_key("hello")
        assert lang == "en-us"  # resolved, not raw

    def test_cache_key_uses_resolved_voice(self):
        """Cache key uses resolved voice."""
        from dictare.tts.kokoro import KokoroTTS

        engine = KokoroTTS(language="it", voice="")
        key, lang, voice = engine._get_cache_key("hello")
        assert voice == "if_sara"  # Italian default

    def test_check_cache_miss(self, tmp_path: Path):
        """check_cache returns None when not cached."""
        from dictare.tts.kokoro import KokoroTTS

        engine = KokoroTTS()
        with patch("dictare.tts.cache._CACHE_DIR", tmp_path):
            assert engine.check_cache("hello") is None

    def test_check_cache_hit(self, tmp_path: Path):
        """check_cache returns path when cached."""
        from dictare.tts.cache import cache_key
        from dictare.tts.kokoro import KokoroTTS

        engine = KokoroTTS(language="en", voice="af_heart")
        key = cache_key("kokoro", "hello", "en-us", "af_heart")
        cached = tmp_path / f"{key}.audio"
        cached.write_bytes(b"audio")

        with patch("dictare.tts.cache._CACHE_DIR", tmp_path):
            result = engine.check_cache("hello")
            assert result == cached
