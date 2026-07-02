"""Tests for AudioManager queue and reconnect behavior."""

from __future__ import annotations

import logging

from dictare.config import AudioConfig
from dictare.core.audio_manager import AudioManager


def _make_manager() -> AudioManager:
    return AudioManager(config=AudioConfig())


class TestQueueAudio:
    """Overflow of the bounded audio queue must never be silent."""

    def test_queue_overflow_drops_oldest_and_logs(self, caplog) -> None:
        mgr = _make_manager()
        for i in range(10):
            mgr.queue_audio(f"utterance-{i}")

        with caplog.at_level(logging.WARNING, logger="dictare.core.audio_manager"):
            mgr.queue_audio("utterance-10")

        assert mgr._queue_drops == 1
        assert any("dropping oldest utterance" in r.message for r in caplog.records)
        # Oldest was discarded, newest is in the queue
        assert mgr.pop_queued_audio() == "utterance-1"

    def test_queue_within_capacity_logs_nothing(self, caplog) -> None:
        mgr = _make_manager()
        with caplog.at_level(logging.WARNING, logger="dictare.core.audio_manager"):
            mgr.queue_audio("utterance-0")

        assert mgr._queue_drops == 0
        assert not caplog.records
