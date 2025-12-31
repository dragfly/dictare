"""Custom exceptions for voxtype."""


class VoxtypeError(Exception):
    """Base exception for voxtype."""

    pass


class AudioError(VoxtypeError):
    """Audio-related errors."""

    pass


class NoMicrophoneError(AudioError):
    """No microphone device found."""

    def __init__(self) -> None:
        super().__init__(
            "No microphone found.\n"
            "Please check:\n"
            "  1. Microphone is connected\n"
            "  2. Run: pactl list sources short\n"
            "  3. Set device in config: audio.device = \"...\""
        )


class STTError(VoxtypeError):
    """Speech-to-text errors."""

    pass


class ModelLoadError(STTError):
    """Failed to load STT model."""

    pass


class HotkeyError(VoxtypeError):
    """Hotkey detection errors."""

    pass


class InputPermissionError(HotkeyError):
    """Insufficient permissions for input device."""

    def __init__(self) -> None:
        super().__init__(
            "Cannot access input devices.\n"
            "Please add your user to the 'input' group:\n"
            "  sudo usermod -aG input $USER\n"
            "Then log out and back in."
        )


class InjectionError(VoxtypeError):
    """Text injection errors."""

    pass


class YdotoolNotRunningError(InjectionError):
    """ydotool daemon not running."""

    def __init__(self) -> None:
        super().__init__(
            "ydotool daemon not running.\n"
            "To fix:\n"
            "  sudo systemctl start ydotoold\n"
            "Or enable at startup:\n"
            "  sudo systemctl enable ydotoold"
        )


class NoInjectorAvailableError(InjectionError):
    """No text injection method available."""

    def __init__(self) -> None:
        super().__init__(
            "No text injection method available.\n"
            "Please install one of:\n"
            "  - ydotool (recommended): sudo apt install ydotool\n"
            "  - wtype (Wayland only): sudo apt install wtype\n"
            "  - xdotool (X11 only): sudo apt install xdotool"
        )
