"""VoxType Engine - Central component containing all services and state.

The Engine is a single process that contains:
- Services (STT, TTS, Translation)
- State (exposed via /status)
- Config (exposed via /config)
- Metrics (exposed via /metrics)
- Transport layer (Unix socket + HTTP)

It can run in:
- Foreground mode: attached to terminal, hotkey registered, console UI
- Daemon mode: detached, no hotkey (Tray registers it), log file output

The code is IDENTICAL for both modes. Only the process management differs.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import TYPE_CHECKING, Any

from voxtype import __version__
from voxtype.engine.control import ControlHandler
from voxtype.engine.server import HTTPServer, UnixSocketServer
from voxtype.engine.state import (
    EngineMetrics,
    EngineState,
    LifetimeMetrics,
    LoadingState,
    SessionMetrics,
    STTState,
)

if TYPE_CHECKING:
    from voxtype.config import Config
    from voxtype.core.engine import VoxtypeEngine as STTService

logger = logging.getLogger(__name__)

def get_voxtype_dir() -> Path:
    """Get the voxtype data directory (~/.voxtype)."""
    return Path.home() / ".voxtype"

def get_socket_path() -> Path:
    """Get the engine socket path."""
    return get_voxtype_dir() / "engine.sock"

def get_pid_path() -> Path:
    """Get the engine PID file path."""
    return get_voxtype_dir() / "engine.pid"

def get_metrics_path() -> Path:
    """Get the metrics file path."""
    return get_voxtype_dir() / "metrics.json"

def get_log_path() -> Path:
    """Get the engine log file path."""
    log_dir = get_voxtype_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "engine.log"

class Engine:
    """VoxType Engine - central component with all services.

    Usage:
        engine = Engine(config)
        engine.start()  # Foreground mode
        # or
        engine.start(daemon=True)  # Daemon mode
    """

    # Graceful shutdown timeout (seconds)
    SHUTDOWN_TIMEOUT = 10

    def __init__(self, config: Config) -> None:
        """Initialize the engine.

        Args:
            config: Application configuration.
        """
        self._config = config
        self._running = False
        self._shutdown_requested = False
        self._start_time: float = 0

        # State
        self.state = EngineState()
        self.metrics = EngineMetrics()

        # Services (initialized on demand)
        self._stt_service: STTService | None = None

        # Transport
        self._http_server: HTTPServer | None = None
        self._socket_server: UnixSocketServer | None = None

        # Control handler
        self._control = ControlHandler(self)

        # Event listeners for SSE
        self._event_listeners: list[Queue[dict | None]] = []
        self._event_lock = threading.Lock()

        # Hotkey handler (foreground mode only)
        self._hotkey_listener: Any = None

    # -------------------------------------------------------------------------
    # Public API - Lifecycle
    # -------------------------------------------------------------------------

    def start(self, *, daemon: bool = False) -> None:
        """Start the engine.

        Args:
            daemon: If True, fork and run as daemon. If False, run in foreground.
        """
        if daemon:
            self._start_daemon()
        else:
            self._start_foreground()

    def stop(self) -> None:
        """Stop the engine gracefully."""
        logger.info("Stopping engine...")
        self._running = False

        # Stop services
        self._stop_stt()

        # Stop transport
        if self._http_server:
            self._http_server.stop()
        if self._socket_server:
            self._socket_server.stop()

        # Notify SSE listeners
        self._broadcast_event(None)  # Signal shutdown

        # Remove PID file
        pid_path = get_pid_path()
        if pid_path.exists():
            try:
                pid_path.unlink()
            except Exception:
                pass

        # Save metrics
        self._save_metrics()

        logger.info("Engine stopped")

    def request_shutdown(self) -> None:
        """Request graceful shutdown (called by control handler)."""
        self._shutdown_requested = True

    # -------------------------------------------------------------------------
    # Public API - Status/Config/Metrics
    # -------------------------------------------------------------------------

    def get_status(self) -> dict:
        """Get current engine state as dict."""
        # Update uptime
        if self._start_time:
            self.state.engine.uptime_seconds = time.time() - self._start_time
        return self.state.to_dict()

    def get_config(self) -> dict:
        """Get current configuration as dict."""
        # Return relevant config sections
        return {
            "engine": {
                "http_port": self._config.server.port,
                "log_level": "info",
            },
            "stt": {
                "mode": "enabled",
                "model": self._config.stt.model,
                "language": self._config.stt.language,
            },
            "tts": {
                "mode": "on-demand",
                "engine": "kokoro",
            },
            "translation": {
                "mode": "disabled",
            },
            "audio": {
                "device": self._config.audio.device,
            },
            "keyboard": {
                "hotkey": self._config.hotkey.key,
            },
            "output": {
                "mode": self._config.output.mode,
            },
        }

    def get_metrics(self) -> dict:
        """Get current metrics as dict."""
        return self.metrics.to_dict()

    def handle_control(self, message: dict) -> dict:
        """Handle OpenVIP control command.

        Args:
            message: OpenVIP control message.

        Returns:
            OpenVIP control response.
        """
        return self._control.handle_command(message)

    # -------------------------------------------------------------------------
    # Public API - Services
    # -------------------------------------------------------------------------

    @property
    def stt_service(self) -> STTService | None:
        """Get the STT service instance."""
        return self._stt_service

    def start_stt(self, *, continuous: bool = True) -> None:
        """Start STT listening.

        Args:
            continuous: If True, continuous mode. If False, one-shot.
        """
        if not self._stt_service:
            raise RuntimeError("STT service not initialized")

        # Update state
        self.state.stt.state = STTState.LISTENING

        # Emit status message
        self._emit_status("stt", "listening")

        # Start listening (actual implementation delegates to existing VoxtypeEngine)
        self._stt_service._set_listening(True)

    def stop_stt(self) -> None:
        """Stop STT listening."""
        if self._stt_service:
            self._stt_service._set_listening(False)
        self.state.stt.state = STTState.IDLE
        self._emit_status("stt", "idle")

    def speak(
        self, text: str, *, voice: str | None = None, speed: float | None = None
    ) -> None:
        """Speak text using TTS.

        Args:
            text: Text to speak.
            voice: Optional voice override.
            speed: Optional speed override.
        """
        # TODO: Implement TTS service integration
        pass

    def stop_tts(self) -> None:
        """Stop TTS playback."""
        # TODO: Implement TTS service integration
        pass

    # -------------------------------------------------------------------------
    # Public API - Event Listeners (for SSE)
    # -------------------------------------------------------------------------

    def register_event_listener(self, queue: Queue[dict | None]) -> None:
        """Register a queue to receive events."""
        with self._event_lock:
            self._event_listeners.append(queue)

    def unregister_event_listener(self, queue: Queue[dict | None]) -> None:
        """Unregister an event listener."""
        with self._event_lock:
            if queue in self._event_listeners:
                self._event_listeners.remove(queue)

    # -------------------------------------------------------------------------
    # Internal - Startup
    # -------------------------------------------------------------------------

    def _start_foreground(self) -> None:
        """Start engine in foreground mode."""
        logger.info("Starting engine in foreground mode...")
        self.state.engine.mode = "foreground"
        self._initialize()

        # Register hotkey
        self._register_hotkey()
        self.state.hotkey.bound = True

        # Keep running until shutdown
        self._main_loop()

    def _start_daemon(self) -> None:
        """Start engine as daemon (fork and detach)."""
        # Fork
        pid = os.fork()
        if pid > 0:
            # Parent: print info and exit
            print(f"Engine started (PID: {pid})")
            return

        # Child: become session leader
        os.setsid()

        # Second fork to prevent zombie
        pid = os.fork()
        if pid > 0:
            os._exit(0)

        # Redirect stdout/stderr to log
        self._redirect_to_log()

        logger.info("Starting engine in daemon mode...")
        self.state.engine.mode = "daemon"
        self._initialize()

        # Do NOT register hotkey in daemon mode
        # Tray will register it and send hotkey.bind

        # Keep running until shutdown
        self._main_loop()

    def _initialize(self) -> None:
        """Initialize engine (common for foreground and daemon)."""
        self._start_time = time.time()
        self._running = True

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Initialize state metadata
        self.state.engine.version = __version__
        self.state.engine.pid = os.getpid()
        self.state.engine.started_at = datetime.now(timezone.utc).isoformat()
        self.state.hotkey.bound = False
        self.state.hotkey.key = self._config.hotkey.key

        # Initialize output state
        self.state.output.mode = self._config.output.mode

        # Load metrics
        self._load_metrics()

        # Write PID file
        self._write_pid()

        # Start transport servers
        self._start_servers()

        # Initialize services based on config
        self._initialize_services()

        logger.info(f"Engine initialized (PID: {os.getpid()}, version: {__version__})")

    def _initialize_services(self) -> None:
        """Initialize services based on configuration."""
        # STT: always enabled for now
        self._initialize_stt()

        # TTS: on-demand (loaded when first used)
        # Translation: disabled (placeholder)

    def _initialize_stt(self) -> None:
        """Initialize STT service."""
        from voxtype.core.engine import create_engine
        from voxtype.core.events import EngineEvents

        # Update loading state
        self.state.loading = LoadingState(
            active=True,
            service="stt",
            stage="loading",
            percent=0,
        )

        # Create event handler that updates engine state
        # Use closure to capture outer self
        outer_self = self

        class STTEventHandler(EngineEvents):
            def __init__(self, engine: Engine) -> None:  # noqa: N805
                self._engine = engine

            def on_state_change(self, old: Any, new: Any, trigger: str) -> None:
                # Map VoxtypeEngine states to STTState
                state_map = {
                    "OFF": STTState.IDLE,
                    "LISTENING": STTState.LISTENING,
                    "RECORDING": STTState.RECORDING,
                    "TRANSCRIBING": STTState.TRANSCRIBING,
                }
                new_state = state_map.get(new.name, STTState.IDLE)
                outer_self.state.stt.state = new_state
                outer_self._emit_status("stt", new_state.value)

            def on_transcription(self, result: Any) -> None:
                # Forward to agents
                outer_self._on_transcription(result)

            def on_partial_transcription(self, text: str) -> None:
                outer_self._emit_partial(text)

            def on_agents_changed(self, agents: list[str]) -> None:
                outer_self.state.output.available_agents = agents

            def on_agent_change(self, name: str, index: int) -> None:
                outer_self.state.output.current_agent = name

            def on_error(self, message: str, context: str) -> None:
                outer_self._emit_error(message, context)

        # Create STT service (reuses existing VoxtypeEngine)
        events = STTEventHandler(self)
        self._stt_service, _ = create_engine(
            config=self._config,
            events=events,
            agent_mode=(self._config.output.mode == "agents"),
            hotkey_enabled=False,  # Engine handles hotkey separately
        )

        # Update state after loading
        self.state.loading = None
        self.state.stt.model_loaded = True
        self.state.stt.model_name = self._config.stt.model
        self.state.stt.language = self._config.stt.language

    def _start_servers(self) -> None:
        """Start transport servers."""
        # Unix socket server
        socket_path = get_socket_path()
        self._socket_server = UnixSocketServer(self, socket_path)
        self._socket_server.start()

        # HTTP server
        self._http_server = HTTPServer(
            self,
            port=self._config.server.port,
            host=self._config.server.host,
        )
        self._http_server.start()

    def _stop_stt(self) -> None:
        """Stop STT service."""
        if self._stt_service:
            self._stt_service.stop()
            self._stt_service = None

    def _register_hotkey(self) -> None:
        """Register hotkey listener (foreground mode only)."""
        # TODO: Implement using existing hotkey system
        pass

    def _write_pid(self) -> None:
        """Write PID file."""
        pid_path = get_pid_path()
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()))

    def _redirect_to_log(self) -> None:
        """Redirect stdout/stderr to log file (daemon mode)."""
        import sys

        log_path = get_log_path()

        # Setup file logging
        handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

        # Redirect stdout/stderr
        sys.stdout = open(log_path, "a")
        sys.stderr = sys.stdout

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self._shutdown_requested = True

    def _main_loop(self) -> None:
        """Main event loop."""
        try:
            while self._running and not self._shutdown_requested:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    # -------------------------------------------------------------------------
    # Internal - Metrics
    # -------------------------------------------------------------------------

    def _load_metrics(self) -> None:
        """Load metrics from disk."""
        import json

        metrics_path = get_metrics_path()
        if metrics_path.exists():
            try:
                data = json.loads(metrics_path.read_text())
                lifetime = data.get("lifetime", {})
                self.metrics.lifetime = LifetimeMetrics(
                    total_transcription_minutes=lifetime.get(
                        "total_transcription_minutes", 0
                    ),
                    total_tts_minutes=lifetime.get("total_tts_minutes", 0),
                    total_sessions=lifetime.get("total_sessions", 0),
                    total_transcriptions=lifetime.get("total_transcriptions", 0),
                    total_tts_requests=lifetime.get("total_tts_requests", 0),
                    first_used=lifetime.get("first_used", ""),
                )
            except Exception as e:
                logger.warning(f"Failed to load metrics: {e}")

        # Initialize session metrics
        self.metrics.session = SessionMetrics(
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        # Increment session count
        self.metrics.lifetime.total_sessions += 1
        if not self.metrics.lifetime.first_used:
            self.metrics.lifetime.first_used = datetime.now(timezone.utc).isoformat()

    def _save_metrics(self) -> None:
        """Save metrics to disk."""
        import json

        metrics_path = get_metrics_path()
        metrics_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = self.metrics.to_dict()
            metrics_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save metrics: {e}")

    # -------------------------------------------------------------------------
    # Internal - Event Emission
    # -------------------------------------------------------------------------

    def _broadcast_event(self, event: dict | None) -> None:
        """Broadcast event to all listeners."""
        with self._event_lock:
            for queue in self._event_listeners:
                try:
                    queue.put_nowait(event)
                except Exception:
                    pass

    def _emit_status(self, service: str, state: str) -> None:
        """Emit status change event."""
        from voxtype.core.openvip import create_status

        # Map to OpenVIP status values
        status_map = {
            "idle": "idle",
            "listening": "listening",
            "recording": "recording",
            "transcribing": "transcribing",
            "error": "error",
        }
        status_value = status_map.get(state, "idle")
        event = create_status(status_value)  # type: ignore
        # Add service info as extension
        event["x_service"] = service
        self._broadcast_event(event)

    def _emit_partial(self, text: str) -> None:
        """Emit partial transcription event."""
        from voxtype.core.openvip import create_partial

        event = create_partial(text)
        self._broadcast_event(event)

    def _emit_error(self, message: str, context: str) -> None:
        """Emit error event."""
        event = {
            "openvip": "1.0",
            "type": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "code": context,
                "message": message,
            },
        }
        self._broadcast_event(event)

    def _on_transcription(self, result: Any) -> None:
        """Handle transcription completion."""
        # Update metrics
        self.metrics.session.transcriptions += 1
        self.metrics.lifetime.total_transcriptions += 1

        # The existing VoxtypeEngine handles agent injection internally
