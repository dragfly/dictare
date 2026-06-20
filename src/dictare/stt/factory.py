"""STT engine factory: selects the engine implementation for model and hardware."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dictare.stt.base import STTEngine

if TYPE_CHECKING:
    from dictare.config import Config


def create_stt_engine(
    config: Config, model_size: str | None = None, *, headless: bool = False
) -> STTEngine:
    """Create and load STT engine.

    Args:
        config: Application config (stt section and log_level are used).
        model_size: Model size to load. If None, uses config.stt.model.
        headless: If True, skip all console output (for Engine/daemon mode).
    """
    from dictare.stt.parakeet import is_parakeet_model
    from dictare.utils.hardware import is_mlx_available

    target_model = model_size or config.stt.model
    engine: STTEngine
    if is_parakeet_model(target_model):
        from dictare.stt.parakeet import ParakeetEngine
        engine = ParakeetEngine()
    elif config.stt.hw_accel and is_mlx_available():
        from dictare.stt.mlx_whisper import MLXWhisperEngine
        engine = MLXWhisperEngine()
    else:
        from dictare.stt.faster_whisper import FasterWhisperEngine
        engine = FasterWhisperEngine()

    engine.load_model(
        model_size or config.stt.model,
        device=config.stt.advanced.device,
        compute_type=config.stt.advanced.compute_type,
        console=None,  # No console in engine
        verbose=config.log_level == "debug",
        headless=headless,
    )

    return engine
