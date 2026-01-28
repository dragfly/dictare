"""Daemon client - communicate with the daemon server."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import TYPE_CHECKING

from voxtype.daemon.protocol import (
    ErrorResponse,
    StatusRequest,
    StatusResponse,
    TTSRequest,
    TTSResponse,
    parse_response,
)

if TYPE_CHECKING:
    from voxtype.config import TTSConfig

def get_socket_path() -> Path:
    """Get path to daemon Unix socket."""
    from voxtype.utils.platform import get_socket_dir

    return get_socket_dir() / "daemon.sock"

def is_daemon_running() -> bool:
    """Check if daemon is running and accepting connections."""
    socket_path = get_socket_path()
    if not socket_path.exists():
        return False

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect(str(socket_path))
        sock.close()
        return True
    except OSError:
        return False

class DaemonClient:
    """Client for communicating with the daemon server."""

    def __init__(self, socket_path: Path | None = None, timeout: float = 30.0):
        """Initialize client.

        Args:
            socket_path: Path to Unix socket. Uses default if None.
            timeout: Socket timeout in seconds.
        """
        self.socket_path = socket_path or get_socket_path()
        self.timeout = timeout

    def _send_request(self, request_json: str) -> bytes:
        """Send request and receive response.

        Args:
            request_json: JSON request string.

        Returns:
            Response bytes.

        Raises:
            ConnectionError: If cannot connect to daemon.
            TimeoutError: If request times out.
        """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)

        try:
            sock.connect(str(self.socket_path))
            sock.sendall(request_json.encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)  # Signal end of request

            # Receive response
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)

            return b"".join(chunks)

        except TimeoutError:
            raise TimeoutError("Request timed out")
        except OSError as e:
            raise ConnectionError(f"Cannot connect to daemon: {e}")
        finally:
            sock.close()

    def send_tts_request(
        self,
        text: str,
        engine: str | None = None,
        language: str | None = None,
        voice: str | None = None,
        speed: int | None = None,
    ) -> TTSResponse | ErrorResponse:
        """Send TTS request to daemon.

        Args:
            text: Text to speak.
            engine: TTS engine name (optional).
            language: Language code (optional).
            voice: Voice name (optional).
            speed: Speech speed (optional).

        Returns:
            TTSResponse on success, ErrorResponse on error.
        """
        request = TTSRequest(
            text=text,
            engine=engine,
            language=language,
            voice=voice,
            speed=speed,
        )

        response_data = self._send_request(request.to_json())
        response = parse_response(response_data)

        if response is None:
            return ErrorResponse(error="Invalid response from daemon", code="INVALID_RESPONSE")

        if isinstance(response, (TTSResponse, ErrorResponse)):
            return response

        return ErrorResponse(error="Unexpected response type", code="UNEXPECTED_RESPONSE")

    def send_tts_request_from_config(
        self,
        text: str,
        config: TTSConfig,
    ) -> TTSResponse | ErrorResponse:
        """Send TTS request using TTSConfig.

        Args:
            text: Text to speak.
            config: TTS configuration.

        Returns:
            TTSResponse on success, ErrorResponse on error.
        """
        return self.send_tts_request(
            text=text,
            engine=config.engine,
            language=config.language,
            voice=config.voice if config.voice else None,
            speed=config.speed,
        )

    def get_status(self) -> StatusResponse | ErrorResponse:
        """Get daemon status.

        Returns:
            StatusResponse on success, ErrorResponse on error.
        """
        request = StatusRequest()
        response_data = self._send_request(request.to_json())
        response = parse_response(response_data)

        if response is None:
            return ErrorResponse(error="Invalid response from daemon", code="INVALID_RESPONSE")

        if isinstance(response, (StatusResponse, ErrorResponse)):
            return response

        return ErrorResponse(error="Unexpected response type", code="UNEXPECTED_RESPONSE")
