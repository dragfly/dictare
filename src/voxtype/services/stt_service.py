"""Speech-to-text service with daemon integration."""

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

    Provides high-level STT API with:
    - Automatic daemon integration when available
    - Fallback to local engine when daemon is not running
    - Lazy model loading
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
        """Check if STT service is available.

        Returns:
            True if daemon is running or local engine can be loaded.
        """
        return self._daemon_available() or self._can_load_local()

    def _daemon_available(self) -> bool:
        """Check if daemon is running and has STT loaded."""
        try:
            from voxtype.daemon.client import DaemonClient, is_daemon_running

            if not is_daemon_running():
                return False

            client = DaemonClient()
            response = client.get_status()
            return hasattr(response, "stt_loaded") and response.stt_loaded
        except Exception:
            return False

    def _can_load_local(self) -> bool:
        """Check if local STT engine can be loaded."""
        # MLX on macOS or faster-whisper on Linux - both are always available to try
        return True

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
        prefer_daemon: bool = True,
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
            prefer_daemon: If True, use daemon when available (faster).

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

        # Use daemon if available and preferred
        if prefer_daemon and self._daemon_available():
            return self._transcribe_via_daemon(
                audio,
                language=lang,
                model_size=model_size,
                hotwords=hw,
                beam_size=beam,
                max_repetitions=max_rep,
                task=task,
            )

        # Fall back to local engine
        engine = self._ensure_engine(model_size)
        return engine.transcribe(
            audio,
            language=lang,
            hotwords=hw,
            beam_size=beam,
            max_repetitions=max_rep,
            task=task,
        )

    def _transcribe_via_daemon(
        self,
        audio: NDArray[np.float32],
        *,
        language: str,
        model_size: str | None,
        hotwords: str | None,
        beam_size: int,
        max_repetitions: int,
        task: str,
    ) -> str:
        """Transcribe audio via daemon.

        Args:
            audio: Audio samples (float32, mono, 16kHz).
            language: Language code.
            model_size: Model size (if different from daemon's loaded model).
            hotwords: Comma-separated words to boost.
            beam_size: Beam size for decoding.
            max_repetitions: Max word repetitions.
            task: "transcribe" or "translate".

        Returns:
            Transcribed text.

        Raises:
            RuntimeError: If daemon returns an error.
        """
        from voxtype.daemon.client import DaemonClient
        from voxtype.daemon.protocol import ErrorResponse

        client = DaemonClient()
        response = client.send_stt_request(
            audio=audio,
            language=language,
            model_size=model_size,
            hotwords=hotwords,
            beam_size=beam_size,
            max_repetitions=max_repetitions,
            task=task,
        )

        if isinstance(response, ErrorResponse):
            raise RuntimeError(f"STT daemon error: {response.error}")

        return response.text

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
