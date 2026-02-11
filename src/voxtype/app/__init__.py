"""App layer — application orchestrator.

AppController is the top-level coordinator for foreground and daemon modes.
It creates VoxtypeEngine (core/), starts the HTTP server, loads models,
and manages keyboard bindings. CLI and tray both use AppController as
their entry point, then run their own UI (StatusPanel or system tray)
in a separate thread, polling /status for engine state.
"""

from voxtype.app.controller import AppController

__all__ = ["AppController"]
