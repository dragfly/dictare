"""Qwen3-TTS backend - high-quality neural text-to-speech with voice cloning.

Features:
- 10 languages (Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian)
- 97ms streaming latency
- Voice cloning from 3 seconds of audio
- Voice design via natural language descriptions

GitHub: https://github.com/QwenLM/Qwen3-TTS
HuggingFace: https://huggingface.co/collections/Qwen/qwen3-tts
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from voxtype.tts.base import TTSEngine


class Qwen3TTS(TTSEngine):
    """TTS using Qwen3-TTS - high-quality neural TTS from Alibaba.

    Install: pip install qwen-tts
    Requires: CUDA GPU recommended (can run on CPU but slow)

    Models (auto-downloaded on first use):
    - Qwen3-TTS-12Hz-0.6B-CustomVoice (smaller, faster)
    - Qwen3-TTS-12Hz-1.7B-CustomVoice (better quality)
    """

    # Supported speakers per language
    SPEAKERS = {
        "en": ["Ryan", "Aiden", "Vivian", "Serena"],
        "zh": ["Uncle_Fu", "Dylan", "Eric"],
        "ja": ["Ono_Anna"],
        "ko": ["Sohee"],
        # Other languages use English speakers with accent
        "de": ["Ryan"],
        "fr": ["Vivian"],
        "it": ["Serena"],
        "es": ["Aiden"],
        "pt": ["Ryan"],
        "ru": ["Eric"],
    }

    # Language code mapping
    LANGUAGE_NAMES = {
        "en": "English",
        "zh": "Chinese",
        "ja": "Japanese",
        "ko": "Korean",
        "de": "German",
        "fr": "French",
        "it": "Italian",
        "es": "Spanish",
        "pt": "Portuguese",
        "ru": "Russian",
    }

    def __init__(
        self,
        language: str = "en",
        speed: int = 175,
        voice: str = "",
        model_size: str = "1.7B",
    ) -> None:
        """Initialize Qwen3 TTS.

        Args:
            language: Language code (en, it, de, zh, ja, ko, etc.).
            speed: Ignored (Qwen3 doesn't support speed control).
            voice: Speaker name. Empty = auto-select based on language.
            model_size: Model size - "0.6B" (faster) or "1.7B" (better quality).
        """
        self.language = language
        self.language_name = self.LANGUAGE_NAMES.get(language, "English")
        self.voice = voice or self._default_voice(language)
        self.model_size = model_size
        self._model: Any = None
        self._available: bool | None = None

    def _default_voice(self, language: str) -> str:
        """Get default voice for language."""
        speakers = self.SPEAKERS.get(language, self.SPEAKERS["en"])
        return speakers[0]

    def _get_model_name(self) -> str:
        """Get HuggingFace model name."""
        return f"Qwen/Qwen3-TTS-12Hz-{self.model_size}-CustomVoice"

    def _load_model(self) -> bool:
        """Lazy load the model on first use."""
        if self._model is not None:
            return True

        try:
            import torch
            from qwen_tts import Qwen3TTSModel

            # Determine device and dtype
            if torch.cuda.is_available():
                device = "cuda:0"
                dtype = torch.bfloat16
                attn_impl = "flash_attention_2"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
                dtype = torch.float16
                attn_impl = "eager"
            else:
                device = "cpu"
                dtype = torch.float32
                attn_impl = "eager"

            self._model = Qwen3TTSModel.from_pretrained(
                self._get_model_name(),
                device_map=device,
                dtype=dtype,
                attn_implementation=attn_impl,
            )
            return True
        except Exception:
            return False

    def is_available(self) -> bool:
        """Check if qwen-tts is available."""
        if self._available is not None:
            return self._available

        try:
            import qwen_tts  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False

        return self._available

    def speak(self, text: str) -> bool:
        """Speak text using Qwen3-TTS.

        Args:
            text: Text to speak.

        Returns:
            True if successful.
        """
        if not self.is_available():
            return False

        if not self._load_model():
            return False

        try:
            import soundfile as sf

            # Generate audio
            wavs, sr = self._model.generate_custom_voice(
                text=text,
                language=self.language_name,
                speaker=self.voice,
            )

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = Path(f.name)

            sf.write(str(wav_path), wavs[0], sr)

            # Play audio
            if sys.platform == "darwin":
                player = ["afplay", str(wav_path)]
            else:
                player = ["aplay", "-q", str(wav_path)]

            subprocess.run(player, capture_output=True, timeout=120)
            wav_path.unlink(missing_ok=True)
            return True

        except Exception:
            return False

    def get_name(self) -> str:
        """Get engine name."""
        return f"qwen3-tts-{self.model_size}"
