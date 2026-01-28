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
    ShutdownRequest,
    StatusRequest,
    StatusResponse,
    TTSRequest,
    TTSResponse,
    parse_request,
)

if TYPE_CHECKING:
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

        return StatusResponse(
            status="ok",
            uptime_seconds=uptime,
            tts_engine=tts_engine,
            tts_loaded=tts_loaded,
            stt_loaded=False,  # Not implemented yet
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

            response: ErrorResponse | TTSResponse | StatusResponse
            if request is None:
                response = ErrorResponse(error="Invalid request", code="INVALID_REQUEST")
            elif isinstance(request, TTSRequest):
                response = self._handle_tts_request(request)
            elif isinstance(request, StatusRequest):
                response = self._handle_status_request(request)
            elif isinstance(request, ShutdownRequest):
                self.running = False
                response = StatusResponse(status="ok", uptime_seconds=0)
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
