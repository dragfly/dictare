"""Tests for agent disconnect while a transcription is in flight.

Pins the CURRENT behavior (read from src/dictare/core/controller.py
_handle_transcription_complete and src/dictare/core/engine.py inject_text):

- The controller does NOT check agent registration.  TranscriptionCompleted
  carries the agent captured at speech-end time, and the controller always
  forwards the text to engine.inject_text with that captured agent.
- The engine trusts the captured Agent object.  If the agent has disconnected
  (send() returns False, e.g. SSEAgent whose SSE queue is gone), the text is
  DROPPED: no retry, no re-queue, no fallback to another agent.  The only
  trace is a JSONL injection log entry with success=False.
- The state machine still recovers to LISTENING, so the user can speak again.

If delivery-failure handling ever becomes smarter (retry/queue), these tests
must be updated deliberately.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

from dictare.core.controller import StateController
from dictare.core.engine import DictareEngine
from dictare.core.fsm import AppState, StateManager, TranscriptionCompleted
from tests.test_engine import MockConfig


def _wait_until(predicate, timeout: float = 2.0) -> None:
    """Poll until predicate is true (1ms interval, no fixed sleep)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.001)

class RecordingEngine:
    """Mock engine recording inject_text calls (test_controller.py idiom)."""

    def __init__(self) -> None:
        self.audio_manager = MagicMock()
        self.audio_manager.sample_rate = 16000
        self.injections: list[tuple[str, Any, str | None]] = []

    def inject_text(self, text: str, agent: Any = None, language: str | None = None) -> None:
        self.injections.append((text, agent, language))

    def process_queued_audio(self) -> None:
        pass

class DisconnectedAgent:
    """Agent whose transport is gone — send() always fails (SSEAgent shape)."""

    def __init__(self, agent_id: str) -> None:
        self._id = agent_id
        self.send_attempts: list[dict] = []

    @property
    def id(self) -> str:
        return self._id

    def send(self, message: dict) -> bool:
        self.send_attempts.append(message)
        return False

# ---------------------------------------------------------------------------
# Controller level
# ---------------------------------------------------------------------------

class TestControllerForwardsToCapturedAgent:
    """The controller never checks registration — it forwards blindly."""

    def test_transcription_forwarded_to_stale_agent(self) -> None:
        """TranscriptionCompleted with a disconnected captured agent is still
        forwarded to engine.inject_text with that exact agent object."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        controller = StateController(sm)
        engine = RecordingEngine()
        controller.set_engine(engine)
        controller.start()

        stale_agent = DisconnectedAgent("claude")
        try:
            controller.send(
                TranscriptionCompleted(text="hello", agent=stale_agent, source="stt")
            )
            _wait_until(lambda: len(engine.injections) == 1)

            assert engine.injections == [("hello", stale_agent, None)]
        finally:
            controller.stop()

    def test_state_recovers_to_listening_after_stale_delivery(self) -> None:
        """Even when the agent is gone, the FSM returns to LISTENING."""
        sm = StateManager(initial_state=AppState.TRANSCRIBING)
        controller = StateController(sm)
        controller.set_engine(RecordingEngine())
        controller.start()

        try:
            controller.send(
                TranscriptionCompleted(
                    text="hello", agent=DisconnectedAgent("claude"), source="stt"
                )
            )
            _wait_until(lambda: sm.state == AppState.LISTENING)
            assert sm.state == AppState.LISTENING
        finally:
            controller.stop()

# ---------------------------------------------------------------------------
# Engine level
# ---------------------------------------------------------------------------

class TestEngineInjectionToDisconnectedAgent:
    """inject_text with a captured agent whose transport is gone."""

    def test_text_is_dropped_with_failed_injection_log(self) -> None:
        """KNOWN LIMITATION (pinned): the text is dropped silently.

        The only trace is log_injection(success=False) — there is no retry,
        no re-queue, and no user-facing error.
        """
        config = MockConfig()
        engine = DictareEngine(config=config)
        engine._logger = MagicMock()

        stale_agent = DisconnectedAgent("claude")
        engine.inject_text("do not lose me", agent=stale_agent)  # Must not raise

        # Delivery was attempted on the captured agent and failed
        assert len(stale_agent.send_attempts) == 1
        assert stale_agent.send_attempts[0]["text"] == "do not lose me"

        # The failure is recorded in the JSONL log...
        engine._logger.log_injection.assert_called_once()
        kwargs = engine._logger.log_injection.call_args.kwargs
        assert kwargs["success"] is False
        assert kwargs["method"] == "agent:claude"

    def test_unregistered_captured_agent_is_still_used(self) -> None:
        """The engine trusts the captured Agent object even if it was
        unregistered from the AgentManager while STT was running."""
        config = MockConfig()
        engine = DictareEngine(config=config)

        # Agent registered at speech-end time...
        stale_agent = DisconnectedAgent("claude")
        engine._agent_mgr._agents["claude"] = stale_agent
        engine._agent_mgr._agent_order.append("claude")
        engine._agent_mgr._current_agent_id = "claude"

        # ...then unregistered mid-transcription
        engine.unregister_agent("claude")

        engine.inject_text("hello", agent=stale_agent)

        # Injection still targets the stale object (no re-resolution)
        assert len(stale_agent.send_attempts) == 1

    def test_no_agent_at_all_logs_method_none(self) -> None:
        """agent=None and no current agent → method 'none', success False."""
        config = MockConfig()
        engine = DictareEngine(config=config)
        engine._agent_mgr._current_agent_id = None
        engine._logger = MagicMock()

        engine.inject_text("hello")  # Must not raise

        kwargs = engine._logger.log_injection.call_args.kwargs
        assert kwargs["method"] == "none"
        assert kwargs["success"] is False
