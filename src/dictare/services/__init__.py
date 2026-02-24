"""Service layer for dictare - high-level APIs for STT, TTS, etc."""

from dictare.services.base import BaseService, ServiceRegistry
from dictare.services.stt_service import STTService
from dictare.services.tts_service import TTSService

__all__ = [
    "BaseService",
    "ServiceRegistry",
    "STTService",
    "TTSService",
]
