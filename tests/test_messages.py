"""Tests for OpenVIP message factory functions."""

from __future__ import annotations

from voxtype.core.messages import (
    OPENVIP_VERSION,
    create_error,
    create_message,
    create_partial,
    create_status,
)

class TestCreateMessage:
    """Test create_message() factory."""

    def test_basic_message(self) -> None:
        """Minimal message has required OpenVIP fields."""
        msg = create_message("hello")
        assert msg["openvip"] == OPENVIP_VERSION
        assert msg["type"] == "transcription"
        assert msg["text"] == "hello"
        assert "id" in msg
        assert "timestamp" in msg
        assert "origin" in msg

    def test_language_field(self) -> None:
        """Language is included when specified."""
        msg = create_message("ciao", language="it")
        assert msg["language"] == "it"

    def test_no_language_by_default(self) -> None:
        """Language is omitted when not specified."""
        msg = create_message("hello")
        assert "language" not in msg

    def test_partial_flag(self) -> None:
        """partial=True sets partial field."""
        msg = create_message("hel", partial=True)
        assert msg["partial"] is True

    def test_no_partial_by_default(self) -> None:
        """partial is omitted when not specified."""
        msg = create_message("hello")
        assert "partial" not in msg

    def test_empty_text(self) -> None:
        """Empty text is valid (used for submit-only messages)."""
        msg = create_message("")
        assert msg["text"] == ""

    def test_unique_ids(self) -> None:
        """Each message gets a unique ID."""
        ids = {create_message("a")["id"] for _ in range(10)}
        assert len(ids) == 10

    def test_no_x_fields(self) -> None:
        """create_message() must NOT add any x_ extension fields.

        Extension fields are the responsibility of pipeline filters.
        """
        msg = create_message("hello", language="en", partial=True)
        x_fields = [k for k in msg if k.startswith("x_")]
        assert x_fields == []

class TestCreatePartial:
    """Test create_partial() convenience function."""

    def test_partial_message(self) -> None:
        """create_partial() returns a message with partial=True."""
        msg = create_partial("hel")
        assert msg["type"] == "transcription"
        assert msg["text"] == "hel"
        assert msg["partial"] is True

class TestCreateStatus:
    """Test create_status() for internal status messages."""

    def test_idle_status(self) -> None:
        """Basic status message."""
        msg = create_status("idle")
        assert msg["type"] == "status"
        assert msg["status"] == "idle"
        assert msg["openvip"] == OPENVIP_VERSION

    def test_error_status_with_details(self) -> None:
        """Error status includes error object."""
        msg = create_status("error", error_message="mic failed", error_code="MIC_ERR")
        assert msg["status"] == "error"
        assert msg["error"]["message"] == "mic failed"
        assert msg["error"]["code"] == "MIC_ERR"

    def test_error_status_without_details(self) -> None:
        """Error status without details omits error object."""
        msg = create_status("error")
        assert msg["status"] == "error"
        assert "error" not in msg

    def test_all_valid_states(self) -> None:
        """All defined states produce valid messages."""
        for state in ("idle", "listening", "recording", "transcribing", "loading", "error"):
            msg = create_status(state)
            assert msg["status"] == state

class TestCreateError:
    """Test create_error() convenience function."""

    def test_error_message(self) -> None:
        """create_error() wraps create_status('error')."""
        msg = create_error("something broke", code="OOPS")
        assert msg["type"] == "status"
        assert msg["status"] == "error"
        assert msg["error"]["message"] == "something broke"
        assert msg["error"]["code"] == "OOPS"

    def test_error_without_code(self) -> None:
        """Error without code still includes message."""
        msg = create_error("boom")
        assert msg["error"]["message"] == "boom"
        assert "code" not in msg["error"]
