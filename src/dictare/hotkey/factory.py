"""Hotkey listener factory: picks the best backend with smart fallback."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from dictare.hotkey.base import HotkeyListener

if TYPE_CHECKING:
    from dictare.config import HotkeyConfig


def create_hotkey_listener(config: HotkeyConfig) -> HotkeyListener:
    """Create hotkey listener with smart fallback."""
    errors: list[str] = []

    # Try evdev first on Linux
    if sys.platform == "linux":
        try:
            from dictare.hotkey.evdev_listener import EvdevHotkeyListener

            # Get target device from config (if user specified one)
            target_device = config.device or None

            modifier = config.mode_switch_modifier
            evdev_listener: HotkeyListener = EvdevHotkeyListener(
                config.key,
                target_device=target_device,
                mode_switch_modifier=modifier,
            )

            # Check if key is available, suggest fallback if not
            if not evdev_listener.is_key_available():
                fallback = EvdevHotkeyListener.suggest_fallback_key()
                if fallback and fallback != config.key:
                    evdev_listener = EvdevHotkeyListener(
                        fallback,
                        target_device=target_device,
                        mode_switch_modifier=modifier,
                    )

            return evdev_listener
        except ImportError:
            errors.append("evdev not installed (pip install evdev)")
        except Exception as e:
            errors.append(f"evdev error: {e}")

    # Fallback to pynput (macOS and X11)
    try:
        from dictare.hotkey.pynput_listener import PynputHotkeyListener

        pynput_listener: HotkeyListener = PynputHotkeyListener(config.key)
        if pynput_listener.is_key_available():
            return pynput_listener
        else:
            errors.append(f"pynput: key {config.key} not supported")
    except ImportError:
        errors.append("pynput not installed (pip install pynput)")
    except Exception as e:
        errors.append(f"pynput error: {e}")

    # No hotkey backend available
    error_details = "\n  - ".join(errors)
    raise RuntimeError(
        f"No hotkey backend available.\n"
        f"Tried:\n  - {error_details}\n\n"
        f"Install evdev (Linux): pip install evdev\n"
        f"Install pynput (macOS/X11): pip install pynput"
    )
