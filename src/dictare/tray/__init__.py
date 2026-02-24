"""VoxType system tray integration."""

from dictare.tray.app import TrayApp
from dictare.tray.lifecycle import get_tray_status, start_tray, stop_tray

__all__ = ["TrayApp", "get_tray_status", "start_tray", "stop_tray"]
