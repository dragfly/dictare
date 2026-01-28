"""VoxType system tray integration."""

from voxtype.tray.app import TrayApp
from voxtype.tray.lifecycle import get_tray_status, start_tray, stop_tray

__all__ = ["TrayApp", "get_tray_status", "start_tray", "stop_tray"]
