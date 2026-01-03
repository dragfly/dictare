"""Device input backends for different platforms.

Available backends:
    - evdev: Linux only, supports device grab
    - hidapi: Cross-platform, no device grab
    - karabiner: macOS only, uses Karabiner-Elements for device grab
"""

from voxtype.input.backends.base import DeviceBackend

__all__ = ["DeviceBackend", "get_available_backends", "get_best_backend"]

def get_available_backends() -> list[str]:
    """Get list of available backend names."""
    available = []

    try:
        from voxtype.input.backends.evdev_backend import EvdevBackend
        if EvdevBackend().is_available():
            available.append("evdev")
    except ImportError:
        pass

    try:
        from voxtype.input.backends.hidapi_backend import HIDAPIBackend
        if HIDAPIBackend().is_available():
            available.append("hidapi")
    except ImportError:
        pass

    try:
        from voxtype.input.backends.karabiner_backend import KarabinerBackend
        if KarabinerBackend().is_available():
            available.append("karabiner")
    except ImportError:
        pass

    return available

def get_best_backend(prefer_grab: bool = True) -> DeviceBackend | None:
    """Get the best available backend.

    Args:
        prefer_grab: If True, prefer backends with device grab support

    Returns:
        Best available backend instance, or None
    """
    import sys

    if sys.platform == "linux":
        try:
            from voxtype.input.backends.evdev_backend import EvdevBackend
            backend = EvdevBackend()
            if backend.is_available():
                return backend
        except ImportError:
            pass

    if sys.platform == "darwin" and prefer_grab:
        try:
            from voxtype.input.backends.karabiner_backend import KarabinerBackend
            backend = KarabinerBackend()
            if backend.is_available():
                return backend
        except ImportError:
            pass

    # Fallback to hidapi (cross-platform, no grab)
    try:
        from voxtype.input.backends.hidapi_backend import HIDAPIBackend
        backend = HIDAPIBackend()
        if backend.is_available():
            return backend
    except ImportError:
        pass

    return None
