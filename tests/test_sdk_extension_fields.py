"""SDK extension field round-trip tests.

Regression guard for the most critical OpenVIP feature: extension fields (x_*).

The entire value proposition of OpenVIP is extensibility. If the SDK drops
unknown fields during deserialization, ALL extension-based features break:
x_input (newline/submit), x_agent_switch, and any vendor-specific x_* field.

These tests verify that extension fields survive the full deserialization
path used by the real code:

    SSE JSON → json.loads() → Transcription.from_dict() → .to_dict() → dict

If someone regenerates the SDK without the post-processing patch
(patch_pydantic_models.py), these tests fail immediately.
"""

from __future__ import annotations

import json

from openvip.models import Transcription

from dictare.pipeline.base import PipelineAction
from dictare.pipeline.executors.input import InputExecutor

# -- Helpers ------------------------------------------------------------------

def _transcription_dict(**extra: object) -> dict:
    """Minimal valid transcription dict, with optional extra fields."""
    d: dict = {
        "openvip": "1.0",
        "type": "transcription",
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": "2026-02-27T10:00:00Z",
        "text": "ciao mondo",
    }
    d.update(extra)
    return d


# -- Core round-trip tests ----------------------------------------------------

class TestExtensionFieldRoundTrip:
    """Extension fields must survive from_dict → to_dict."""

    def test_x_input_newline_survives(self) -> None:
        data = _transcription_dict(x_input={"ops": ["newline"]})
        t = Transcription.from_dict(data)
        result = t.to_dict()
        assert result["x_input"] == {"ops": ["newline"]}

    def test_x_input_submit_survives(self) -> None:
        data = _transcription_dict(x_input={"ops": ["submit"]})
        t = Transcription.from_dict(data)
        result = t.to_dict()
        assert result["x_input"] == {"ops": ["submit"]}

    def test_x_agent_switch_survives(self) -> None:
        data = _transcription_dict(x_agent_switch={"target": "claude"})
        t = Transcription.from_dict(data)
        result = t.to_dict()
        assert result["x_agent_switch"] == {"target": "claude"}

    def test_vendor_extension_survives(self) -> None:
        data = _transcription_dict(x_bticino={"device": "light", "action": "on"})
        t = Transcription.from_dict(data)
        result = t.to_dict()
        assert result["x_bticino"] == {"device": "light", "action": "on"}

    def test_multiple_extensions_survive(self) -> None:
        data = _transcription_dict(
            x_input={"ops": ["newline"]},
            x_flags={"urgent": True},
        )
        t = Transcription.from_dict(data)
        result = t.to_dict()
        assert result["x_input"] == {"ops": ["newline"]}
        assert result["x_flags"] == {"urgent": True}

    def test_known_fields_unaffected(self) -> None:
        """Sanity: extra='allow' doesn't break known field handling."""
        data = _transcription_dict(language="it", confidence=0.95)
        t = Transcription.from_dict(data)
        assert t.text == "ciao mondo"
        assert t.language == "it"
        assert t.confidence == 0.95


# -- JSON → SDK → dict (simulates the SSE receive path) ----------------------

class TestSSEDeserializationPath:
    """Simulate the exact path used by client.subscribe().

    SSE payload → json.loads() → Transcription.from_dict() → .to_dict()
    This is the path that broke when the SDK was regenerated without patches.
    """

    def test_x_input_survives_json_roundtrip(self) -> None:
        """The exact failure scenario: SSE JSON with x_input."""
        sse_payload = json.dumps({
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-27T10:00:00Z",
            "text": "hello world",
            "x_input": {"ops": ["newline"]},
        })

        # This is what client._parse_agent_message() does:
        raw = json.loads(sse_payload)
        msg = Transcription.from_dict(raw)

        # This is what mux._read_from_sse() does:
        msg_dict = msg.to_dict()

        assert "x_input" in msg_dict, (
            "x_input dropped by SDK deserialization! "
            "Did you regenerate without patch_pydantic_models.py?"
        )
        assert msg_dict["x_input"] == {"ops": ["newline"]}

    def test_x_input_submit_survives_json_roundtrip(self) -> None:
        sse_payload = json.dumps({
            "openvip": "1.0",
            "type": "transcription",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-27T10:00:00Z",
            "text": "send this",
            "x_input": {"ops": ["submit"], "trigger": "ok send", "confidence": 0.9},
        })

        raw = json.loads(sse_payload)
        msg = Transcription.from_dict(raw)
        msg_dict = msg.to_dict()

        assert "submit" in msg_dict["x_input"]["ops"]
        assert msg_dict["x_input"]["trigger"] == "ok send"


# -- InputExecutor integration (SDK → executor) ------------------------------

class TestInputExecutorWithSDK:
    """Verify InputExecutor finds x_input after SDK deserialization.

    This is the end-to-end path that broke: the SDK dropped x_input,
    so InputExecutor never saw it and returned PASS instead of CONSUMED.
    """

    def test_newline_detected_after_sdk_roundtrip(self) -> None:
        data = _transcription_dict(x_input={"ops": ["newline"]})
        msg = Transcription.from_dict(data)
        msg_dict = msg.to_dict()

        calls: list[tuple[str, bool]] = []
        executor = InputExecutor(write_fn=lambda text, submit: calls.append((text, submit)))
        result = executor.process(msg_dict)

        assert result.action == PipelineAction.CONSUME
        assert len(calls) == 1
        assert calls[0][0] == "ciao mondo\n"  # newline appended
        assert calls[0][1] is False  # submit=False

    def test_submit_detected_after_sdk_roundtrip(self) -> None:
        data = _transcription_dict(x_input={"ops": ["submit"]})
        msg = Transcription.from_dict(data)
        msg_dict = msg.to_dict()

        calls: list[tuple[str, bool]] = []
        executor = InputExecutor(write_fn=lambda text, submit: calls.append((text, submit)))
        result = executor.process(msg_dict)

        assert result.action == PipelineAction.CONSUME
        assert len(calls) == 1
        assert calls[0][1] is True  # submit=True

    def test_no_x_input_passes_through(self) -> None:
        data = _transcription_dict()  # no x_input
        msg = Transcription.from_dict(data)
        msg_dict = msg.to_dict()

        executor = InputExecutor(write_fn=lambda text, submit: None)
        result = executor.process(msg_dict)

        assert result.action == PipelineAction.PASS
