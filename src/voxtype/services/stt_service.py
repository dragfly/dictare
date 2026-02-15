"""Speech-to-text service."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from voxtype.services.base import BaseService

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from voxtype.config import Config
    from voxtype.stt.base import STTEngine


class STTService(BaseService):
    """Speech-to-text service.

    Provides high-level STT API with lazy model loading.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize STT service.

        Args:
            config: Configuration object. If None, loads default config.
        """
        super().__init__(config)
        self._engine: STTEngine | None = None
        self._engine_model_size: str | None = None

    @property
    def name(self) -> str:
        """Get service name."""
        return "stt"

    def is_available(self) -> bool:
        """Check if STT service is available."""
        return True  # MLX on macOS or faster-whisper on Linux

    def _ensure_engine(self, model_size: str | None = None, *, headless: bool = False) -> STTEngine:
        """Ensure local STT engine is loaded.

        Args:
            model_size: Model size to load. If None, uses config.stt.model.
            headless: If True, skip all console output (for Engine/daemon mode).

        Returns:
            Loaded STT engine.
        """
        target_size = model_size or self.config.stt.model

        # Reload if model size changed
        if self._engine is not None and self._engine_model_size != target_size:
            self._engine = None

        if self._engine is None:
            from voxtype.utils.hardware import is_mlx_available

            use_mlx = self.config.stt.hw_accel and is_mlx_available()

            if use_mlx:
                from voxtype.stt.mlx_whisper import MLXWhisperEngine

                self._engine = MLXWhisperEngine()
            else:
                from voxtype.stt.faster_whisper import FasterWhisperEngine

                self._engine = FasterWhisperEngine()

            self._engine.load_model(
                target_size,
                device=self.config.stt.device,
                compute_type=self.config.stt.compute_type,
                verbose=self.config.verbose,
                headless=headless,
            )
            self._engine_model_size = target_size

        return self._engine

    def transcribe(
        self,
        audio: NDArray[np.float32],
        *,
        language: str | None = None,
        model_size: str | None = None,
        hotwords: str | None = None,
        beam_size: int | None = None,
        max_repetitions: int | None = None,
        task: str = "transcribe",
    ) -> str:
        """Transcribe audio to text.

        Args:
            audio: Audio samples (float32, mono, 16kHz).
            language: Language code or None for config default ("auto" for detection).
            model_size: Model size override (default uses config.stt.model).
            hotwords: Comma-separated words to boost recognition.
            beam_size: Beam size for decoding.
            max_repetitions: Max consecutive word repetitions before filtering.
            task: "transcribe" for same-language, "translate" for English output.

        Returns:
            Transcribed (or translated) text.
        """
        lang = language if language is not None else self.config.stt.language
        hw = hotwords if hotwords is not None else (self.config.stt.hotwords or None)
        beam = beam_size if beam_size is not None else self.config.stt.beam_size
        max_rep = (
            max_repetitions
            if max_repetitions is not None
            else self.config.stt.max_repetitions
        )

        engine = self._ensure_engine(model_size)
        result = engine.transcribe(
            audio,
            language=lang,
            hotwords=hw,
            beam_size=beam,
            max_repetitions=max_rep,
            task=task,
        )
        return result.text

    def transcribe_file(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        model_size: str | None = None,
        task: str = "transcribe",
    ) -> str:
        """Transcribe audio from a file.

        Args:
            audio_path: Path to audio file (wav, mp3, flac, etc.).
            language: Language code or None for auto-detection.
            model_size: Model size override.
            task: "transcribe" or "translate".

        Returns:
            Transcribed text.
        """
        import soundfile as sf

        audio, sample_rate = sf.read(str(audio_path), dtype="float32")

        # Resample to 16kHz if needed
        if sample_rate != 16000:
            import librosa

            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)

        # Convert to mono if stereo
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)

        return self.transcribe(
            audio,
            language=language,
            model_size=model_size,
            task=task,
        )

    def translate(
        self,
        audio: NDArray[np.float32],
        *,
        model_size: str | None = None,
    ) -> str:
        """Translate audio to English.

        This is a convenience wrapper for transcribe(task="translate").

        Args:
            audio: Audio samples (float32, mono, 16kHz).
            model_size: Model size override.

        Returns:
            Translated English text.
        """
        return self.transcribe(audio, model_size=model_size, task="translate")

    def is_loaded(self) -> bool:
        """Check if local engine is loaded."""
        return self._engine is not None and self._engine.is_loaded()
