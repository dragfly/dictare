"""Daemon server - Unix socket server with cached TTS/STT models."""

from __future__ import annotations

import atexit
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from voxtype.daemon.lifecycle import get_socket_path, remove_pid, write_pid
from voxtype.daemon.protocol import (
    ErrorResponse,
    ListenResponse,
    ListenStartRequest,
    ListenStopRequest,
    ListenToggleRequest,
    ModeSetRequest,
    OkResponse,
    ProcessingModeResponse,
    ProcessingModeToggleRequest,
    ShutdownRequest,
    StatusRequest,
    StatusResponse,
    TTSRequest,
    TTSResponse,
    parse_request,
)

if TYPE_CHECKING:
    from voxtype.core.engine import VoxtypeEngine
    from voxtype.tts.base import TTSEngine

class DaemonServer:
    """Unix socket server that keeps TTS/STT models loaded."""

    def __init__(self, socket_path: Path | None = None):
        """Initialize daemon server.

        Args:
            socket_path: Path to Unix socket. Uses default if None.
        """
        self.socket_path = socket_path or get_socket_path()
        self.socket: socket.socket | None = None
        self.running = False
        self.start_time = time.time()
        self.requests_served = 0
        self.lock = threading.Lock()

        # Cached engines
        self._tts_cache: dict[str, TTSEngine] = {}
        self._tts_lock = threading.Lock()

        # Current default config (loaded lazily)
        self._config = None

        # Loading state tracking
        self._state: str = "off"  # "loading" | "listening" | "muted" | "off"
        self._progress: int = 0  # 0-100
        self._loading_stage: str = ""  # "STT" | "VAD" | ""
        self._state_lock = threading.Lock()

        # Voice engine (loaded lazily on first listen request)
        self._engine: VoxtypeEngine | None = None
        self._engine_thread: threading.Thread | None = None
        self._engine_lock = threading.Lock()

        # Output mode tracking
        self._output_mode: str = "keyboard"  # "keyboard" | "agents"

    def set_state(
        self,
        state: str,
        progress: int = 0,
        loading_stage: str = "",
    ) -> None:
        """Set the daemon state (called externally to update status).

        Args:
            state: Current state ("loading", "listening", "muted", "off")
            progress: Loading progress 0-100 (only relevant when loading)
            loading_stage: What is currently loading ("STT", "VAD", "")
        """
        with self._state_lock:
            self._state = state
            self._progress = progress
            self._loading_stage = loading_stage

    def _load_config(self):
        """Load configuration lazily."""
        if self._config is None:
            from voxtype.config import load_config

            self._config = load_config()
        return self._config

    def _get_tts_engine(
        self,
        engine: str | None = None,
        language: str | None = None,
        voice: str | None = None,
        speed: int | None = None,
    ):
        """Get or create cached TTS engine.

        Args:
            engine: TTS engine name.
            language: Language code.
            voice: Voice name.
            speed: Speech speed.

        Returns:
            Cached or newly created TTSEngine.
        """
        from voxtype.config import TTSConfig
        from voxtype.tts import create_tts_engine

        config = self._load_config()

        # Build cache key from relevant parameters
        engine_name = engine or config.tts.engine
        lang = language or config.tts.language
        voice_name = voice or config.tts.voice
        spd = speed or config.tts.speed

        cache_key = f"{engine_name}:{lang}:{voice_name}:{spd}"

        with self._tts_lock:
            if cache_key not in self._tts_cache:
                tts_config = TTSConfig(
                    engine=engine_name,  # type: ignore[arg-type]
                    language=lang,
                    voice=voice_name,
                    speed=spd,
                )
                self._tts_cache[cache_key] = create_tts_engine(tts_config)

            return self._tts_cache[cache_key]

    def _handle_tts_request(self, request: TTSRequest) -> TTSResponse | ErrorResponse:
        """Handle TTS request.

        Args:
            request: TTS request.

        Returns:
            Response with duration or error.
        """
        try:
            engine = self._get_tts_engine(
                engine=request.engine,
                language=request.language,
                voice=request.voice,
                speed=request.speed,
            )

            start_time = time.time()
            engine.speak(request.text)
            duration_ms = int((time.time() - start_time) * 1000)

            return TTSResponse(status="ok", duration_ms=duration_ms)

        except ValueError as e:
            return ErrorResponse(error=str(e), code="TTS_ERROR")
        except Exception as e:
            return ErrorResponse(error=str(e), code="INTERNAL_ERROR")

    def _create_engine(self, start_listening: bool = False) -> None:
        """Create and start the voice engine in a background thread.

        Args:
            start_listening: If True, transition to LISTENING after init.
                           If False, stay in OFF state.
        """
        from voxtype.config import load_config
        from voxtype.core.engine import VoxtypeEngine

        config = load_config()
        self._output_mode = config.output.mode

        # Determine if agent mode based on output mode
        agent_mode = self._output_mode == "agents"

        # Event to signal when engine is ready
        engine_ready = threading.Event()

        # Event handler to capture on_engine_ready
        class DaemonEvents:
            def on_engine_ready(self) -> None:
                engine_ready.set()

            def on_state_change(self, old, new, trigger) -> None:
                pass  # We sync state after ready

        self._engine = VoxtypeEngine(
            config=config,
            agent_mode=agent_mode,
            events=DaemonEvents(),
        )

        # Start engine in background thread
        def run_engine() -> None:
            if self._engine:
                self.set_state("loading", 0, "STT")
                self._engine.start(start_listening=start_listening)

        self._engine_thread = threading.Thread(target=run_engine, daemon=True)
        self._engine_thread.start()

        # Wait for engine ready signal (with timeout)
        if not engine_ready.wait(timeout=60.0):
            raise TimeoutError("Engine failed to initialize within 60 seconds")

        # Update state based on engine state
        if self._engine:
            if self._engine.is_listening:
                self.set_state("listening")
            else:
                self.set_state("off")

    def _handle_listen_start(self, request: ListenStartRequest) -> ListenResponse | ErrorResponse:
        """Handle listen.start request."""
        try:
            needs_create = False
            with self._engine_lock:
                if self._engine is None:
                    needs_create = True
                elif self._engine.is_off:
                    self._engine._set_listening(True)
                    self.set_state("listening")

            # Create engine outside lock to avoid blocking other requests
            if needs_create:
                self._create_engine(start_listening=True)

            listening = self._engine.is_listening if self._engine else False
            return ListenResponse(status="ok", listening=listening)
        except Exception as e:
            return ErrorResponse(error=str(e), code="ENGINE_ERROR")

    def _handle_listen_stop(self, request: ListenStopRequest) -> ListenResponse | ErrorResponse:
        """Handle listen.stop request."""
        try:
            with self._engine_lock:
                if self._engine and self._engine.is_listening:
                    self._engine._set_listening(False)

            self.set_state("off")
            return ListenResponse(status="ok", listening=False)
        except Exception as e:
            return ErrorResponse(error=str(e), code="ENGINE_ERROR")

    def _handle_listen_toggle(self, request: ListenToggleRequest) -> ListenResponse | ErrorResponse:
        """Handle listen.toggle request."""
        try:
            needs_create = False
            with self._engine_lock:
                if self._engine is None:
                    needs_create = True
                else:
                    # Engine exists: toggle its state
                    self._engine._toggle_listening()
                    # Sync daemon state with engine state
                    if self._engine.is_listening:
                        self.set_state("listening")
                    else:
                        self.set_state("off")

            # Create engine outside lock to avoid blocking other requests
            if needs_create:
                self._create_engine(start_listening=True)

            listening = self._engine.is_listening if self._engine else False
            return ListenResponse(status="ok", listening=listening)
        except Exception as e:
            return ErrorResponse(error=str(e), code="ENGINE_ERROR")

    def _handle_mode_set(self, request: ModeSetRequest) -> OkResponse | ErrorResponse:
        """Handle mode.set request."""
        try:
            from voxtype.config import set_config_value

            mode = request.mode
            if mode not in ("keyboard", "agents"):
                return ErrorResponse(error=f"Invalid mode: {mode}", code="INVALID_MODE")

            self._output_mode = mode
            set_config_value("output.mode", mode)

            # Note: changing mode while engine is running would require restart
            # For now, just update the config - next engine start will use new mode
            return OkResponse()
        except Exception as e:
            return ErrorResponse(error=str(e), code="CONFIG_ERROR")

    def _handle_processing_mode_toggle(
        self, request: ProcessingModeToggleRequest
    ) -> ProcessingModeResponse | ErrorResponse:
        """Handle processing_mode.toggle request."""
        try:
            with self._engine_lock:
                if self._engine is None:
                    return ErrorResponse(error="Engine not running", code="ENGINE_NOT_RUNNING")

                # Toggle processing mode (transcription <-> command)
                self._engine._switch_processing_mode()
                new_mode = self._engine.mode.value  # "transcription" or "command"

            return ProcessingModeResponse(status="ok", processing_mode=new_mode)
        except Exception as e:
            return ErrorResponse(error=str(e), code="ENGINE_ERROR")

    def _handle_status_request(self, request: StatusRequest) -> StatusResponse:
        """Handle status request.

        Args:
            request: Status request.

        Returns:
            Status response.
        """
        uptime = time.time() - self.start_time

        with self._tts_lock:
            tts_loaded = len(self._tts_cache) > 0
            tts_engine = list(self._tts_cache.keys())[0] if self._tts_cache else None

        with self._state_lock:
            state = self._state
            progress = self._progress
            loading_stage = self._loading_stage

        # Get engine state
        current_agent: str | None = None
        available_agents: list[str] = []
        stt_loaded = False
        processing_mode = "transcription"

        with self._engine_lock:
            if self._engine:
                current_agent = self._engine.current_agent
                available_agents = list(self._engine.agents)
                stt_loaded = self._engine._stt is not None
                processing_mode = self._engine.mode.value

        return StatusResponse(
            status="ok",
            state=state,  # type: ignore[arg-type]
            processing_mode=processing_mode,  # type: ignore[arg-type]
            progress=progress,
            loading_stage=loading_stage,
            output_mode=self._output_mode,
            current_agent=current_agent,
            available_agents=available_agents,
            uptime_seconds=uptime,
            tts_engine=tts_engine,
            tts_loaded=tts_loaded,
            stt_loaded=stt_loaded,
            requests_served=self.requests_served,
        )

    def _handle_client(self, conn: socket.socket, addr) -> None:
        """Handle a client connection.

        Args:
            conn: Client socket.
            addr: Client address.
        """
        try:
            # Read request
            chunks = []
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)

            data = b"".join(chunks)
            if not data:
                return

            # Parse and handle request
            request = parse_request(data)

            response: ErrorResponse | TTSResponse | StatusResponse | ListenResponse | ProcessingModeResponse | OkResponse
            if request is None:
                response = ErrorResponse(error="Invalid request", code="INVALID_REQUEST")
            elif isinstance(request, TTSRequest):
                response = self._handle_tts_request(request)
            elif isinstance(request, StatusRequest):
                response = self._handle_status_request(request)
            elif isinstance(request, ShutdownRequest):
                self.running = False
                response = OkResponse()
            elif isinstance(request, ListenStartRequest):
                response = self._handle_listen_start(request)
            elif isinstance(request, ListenStopRequest):
                response = self._handle_listen_stop(request)
            elif isinstance(request, ListenToggleRequest):
                response = self._handle_listen_toggle(request)
            elif isinstance(request, ModeSetRequest):
                response = self._handle_mode_set(request)
            elif isinstance(request, ProcessingModeToggleRequest):
                response = self._handle_processing_mode_toggle(request)
            else:
                response = ErrorResponse(error="Unknown request type", code="UNKNOWN_REQUEST")

            # Send response
            conn.sendall(response.to_json().encode("utf-8"))

            with self.lock:
                self.requests_served += 1

        except Exception as e:
            try:
                error = ErrorResponse(error=str(e), code="INTERNAL_ERROR")
                conn.sendall(error.to_json().encode("utf-8"))
            except Exception:
                pass
        finally:
            conn.close()

    def _cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass

        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except Exception:
                pass

        remove_pid()

    def run(self) -> None:
        """Run the daemon server (blocking)."""
        # Remove stale socket
        if self.socket_path.exists():
            self.socket_path.unlink()

        # Create socket
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(str(self.socket_path))
        self.socket.listen(5)
        self.socket.settimeout(1.0)  # For clean shutdown

        # Write PID file
        write_pid(os.getpid())

        # Register cleanup
        atexit.register(self._cleanup)

        def signal_handler(signum, frame):
            self.running = False

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        self.running = True
        self.start_time = time.time()

        print(f"Daemon started, listening on {self.socket_path}")
        sys.stdout.flush()

        while self.running:
            try:
                conn, addr = self.socket.accept()
                # Handle in thread for concurrency
                thread = threading.Thread(target=self._handle_client, args=(conn, addr))
                thread.daemon = True
                thread.start()
            except TimeoutError:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")
                    sys.stdout.flush()

        print("Daemon shutting down...")
        sys.stdout.flush()
        self._cleanup()

def main():
    """Entry point for running daemon as module."""
    server = DaemonServer()
    server.run()

if __name__ == "__main__":
    main()
