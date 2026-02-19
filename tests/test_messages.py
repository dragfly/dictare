"""Tests for OpenVIP message factory functions."""

from __future__ import annotations

from voxtype.core.openvip_messages import (
    OPENVIP_VERSION,
    create_message,
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


