"""Tests for agent/injection/base.py — sanitize_text_for_injection and TextInjector."""

from __future__ import annotations

from dictare.agent.injection.base import TextInjector, sanitize_text_for_injection


class TestSanitizeTextForInjection:
    def test_plain_text_unchanged(self) -> None:
        assert sanitize_text_for_injection("hello world") == "hello world"

    def test_removes_csi_sequences(self) -> None:
        # CSI color codes: ESC [ 31m
        text = "\x1b[31mred text\x1b[0m"
        result = sanitize_text_for_injection(text)
        assert result == "red text"

    def test_removes_osc_sequences_bel(self) -> None:
        # OSC with BEL terminator
        text = "\x1b]0;title\x07some text"
        result = sanitize_text_for_injection(text)
        assert result == "some text"

    def test_removes_osc_sequences_st(self) -> None:
        # OSC with ST terminator
        text = "\x1b]0;title\x1b\\some text"
        result = sanitize_text_for_injection(text)
        assert result == "some text"

    def test_removes_bracketed_paste_sequences(self) -> None:
        text = "[27;2;13~hello"
        result = sanitize_text_for_injection(text)
        assert result == "hello"

    def test_preserves_tabs_and_newlines(self) -> None:
        text = "line1\n\tindented\r\nline3"
        result = sanitize_text_for_injection(text)
        assert result == "line1\n\tindented\r\nline3"

    def test_removes_control_characters(self) -> None:
        # Bell, backspace, form feed
        text = "hello\x07\x08\x0cworld"
        result = sanitize_text_for_injection(text)
        assert result == "helloworld"

    def test_removes_delete_character(self) -> None:
        text = "hello\x7fworld"
        result = sanitize_text_for_injection(text)
        assert result == "helloworld"

    def test_preserves_unicode(self) -> None:
        text = "ciao mondo! 日本語"
        result = sanitize_text_for_injection(text)
        assert result == "ciao mondo! 日本語"

    def test_empty_string(self) -> None:
        assert sanitize_text_for_injection("") == ""

    def test_only_escape_sequences(self) -> None:
        text = "\x1b[31m\x1b[0m"
        result = sanitize_text_for_injection(text)
        assert result == ""

    def test_complex_ansi_with_params(self) -> None:
        # 256 color: ESC[38;5;210m
        text = "\x1b[38;5;210mcolored\x1b[0m"
        result = sanitize_text_for_injection(text)
        assert result == "colored"


class ConcreteInjector(TextInjector):
    """Concrete implementation for testing abstract base."""

    def is_available(self) -> bool:
        return True

    def type_text(self, text, delay_ms=0, auto_submit=True, submit_keys="enter", newline_keys="alt+enter") -> bool:
        return True

    def get_name(self) -> str:
        return "test-injector"


class TestTextInjector:
    def test_send_newline_default_false(self) -> None:
        injector = ConcreteInjector()
        assert injector.send_newline() is False

    def test_send_submit_default_false(self) -> None:
        injector = ConcreteInjector()
        assert injector.send_submit() is False

    def test_is_available(self) -> None:
        injector = ConcreteInjector()
        assert injector.is_available() is True

    def test_get_name(self) -> None:
        injector = ConcreteInjector()
        assert injector.get_name() == "test-injector"

    def test_type_text(self) -> None:
        injector = ConcreteInjector()
        assert injector.type_text("hello") is True
