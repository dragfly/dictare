"""Tests for voxtype.tray.app — _ensure_accessibility()."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

def test_ensure_accessibility_noop_on_linux(monkeypatch: object) -> None:
    """On non-macOS, _ensure_accessibility always returns True."""
    monkeypatch.setattr(sys, "platform", "linux")

    from voxtype.tray.app import _ensure_accessibility

    assert _ensure_accessibility() is True

def test_ensure_accessibility_returns_false_on_exception(monkeypatch: object) -> None:
    """If ctypes fails, returns False gracefully."""
    monkeypatch.setattr(sys, "platform", "darwin")

    with patch("ctypes.cdll") as mock_cdll:
        mock_cdll.LoadLibrary.side_effect = OSError("no framework")

        from importlib import reload

        import voxtype.tray.app as tray_mod

        reload(tray_mod)
        result = tray_mod._ensure_accessibility()

    assert result is False

def test_ensure_accessibility_calls_ax_api(monkeypatch: object) -> None:
    """Verifies the correct CoreFoundation/ApplicationServices calls are made."""
    monkeypatch.setattr(sys, "platform", "darwin")

    mock_appserv = MagicMock()
    mock_cf = MagicMock()

    # AXIsProcessTrustedWithOptions returns True
    mock_appserv.AXIsProcessTrustedWithOptions.return_value = True

    # kAXTrustedCheckOptionPrompt symbol
    mock_appserv.kAXTrustedCheckOptionPrompt = MagicMock()

    # kCFBooleanTrue symbol
    mock_cf.kCFBooleanTrue = MagicMock()

    # CFDictionaryCreateMutable returns a fake dict pointer
    mock_cf.CFDictionaryCreateMutable.return_value = 0xDEAD

    def load_library(path: str) -> MagicMock:
        if "ApplicationServices" in path:
            return mock_appserv
        return mock_cf

    with patch("ctypes.cdll") as mock_cdll:
        mock_cdll.LoadLibrary = load_library
        # c_void_p.in_dll needs to return the mock symbols
        with patch("ctypes.c_void_p") as mock_c_void_p:
            def in_dll(lib: MagicMock, name: str) -> MagicMock:
                return getattr(lib, name)

            mock_c_void_p.in_dll = in_dll

            from importlib import reload

            import voxtype.tray.app as tray_mod

            reload(tray_mod)
            result = tray_mod._ensure_accessibility(prompt=True)

    assert result is True
    mock_appserv.AXIsProcessTrustedWithOptions.assert_called_once()
    mock_cf.CFDictionarySetValue.assert_called_once()
    mock_cf.CFRelease.assert_called_once()
