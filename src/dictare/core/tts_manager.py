"""TTS engine loading, worker management, and speech methods.

Extracted from DictareEngine to reduce god-object complexity.
The engine delegates all TTS-related state and operations here.
"""

from __future__ import annotations

import json
import logging
import secrets
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dictare.config import Config
    from dictare.core.controller import StateController

logger = logging.getLogger(__name__)

# Seconds to wait for the TTS worker subprocess to connect via SSE
_TTS_WORKER_CONNECT_TIMEOUT: float = 120.0

# Seconds to wait for the TTS worker to exit gracefully before killing
_TTS_WORKER_STOP_TIMEOUT: float = 5.0


class TTSManager:
    """Manages TTS engine loading, worker subprocess, and speech.

    Owns all TTS-related state:
    - Engine instance (_tts_engine, _tts_proxy)
    - Worker subprocess (_tts_worker_process)
    - Play counter for mic-pausing (_active_plays, _play_lock)
    - Auth token for worker registration
    - Loading progress status

    Side effects (mic pausing via PlayStarted/PlayCompleted) are dispatched
    via the StateController passed at construction.
    """

    def __init__(
        self,
        config: Config,
        *,
        controller: StateController | None = None,
    ) -> None:
        self._config = config
        self._controller = controller

        # TTS engine (loaded at startup, None if unavailable)
        self._tts_engine: Any = None
        self._tts_error: str = ""
        self._tts_proxy: Any = None  # WorkerTTSEngine (set when using worker)
        self._tts_worker_process: Any = None  # subprocess.Popen for TTS worker

        # Play counter for mic-pausing: mic stays paused while any play is active.
        # Incremented before speak(), decremented after. 0→1 pauses mic, N→0 resumes.
        self._active_plays = 0
        self._play_lock = threading.Lock()

        # Scoped auth token for TTS worker registration
        self._auth_token = secrets.token_hex(32)  # hex-only: never starts with '-' (argparse-safe)

        # Loading progress (read by engine for /status)
        self._loading_status: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def engine(self) -> Any:
        """The loaded TTS engine instance (or None)."""
        return self._tts_engine

    @property
    def available(self) -> bool:
        """True if a TTS engine is loaded and ready."""
        return self._tts_engine is not None

    @property
    def error(self) -> str:
        """Error message if TTS loading failed, empty string otherwise."""
        return self._tts_error

    @property
    def auth_token(self) -> str:
        """Scoped auth token for TTS worker registration."""
        return self._auth_token

    @property
    def loading_status(self) -> dict[str, Any]:
        """Loading progress dict for /status endpoint."""
        return self._loading_status

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(
        self,
        *,
        http_server: Any = None,
        estimated: float = 1,
    ) -> None:
        """Load TTS engine (in-process or via worker subprocess).

        Args:
            http_server: OpenVIPServer instance (enables worker mode for
                heavy engines like outetts/piper/coqui).
            estimated: Estimated load time in seconds (for progress UI).
        """
        from dictare.tts.venv import VENV_ENGINES
        from dictare.utils.stats import save_model_load_time

        engine_name = self._config.tts.engine
        _worker_engines = set(VENV_ENGINES.keys())
        use_worker = engine_name in _worker_engines and http_server is not None

        self._loading_status = {
            "name": "tts",
            "status": "loading",
            "start_time": time.time(),
            "elapsed": 0,
            "estimated": estimated,
        }

        logger.debug("Loading TTS engine: %s (worker=%s)", engine_name, use_worker)

        if use_worker:
            try:
                self._spawn_worker(http_server)
                elapsed = round(time.time() - self._loading_status["start_time"], 1)
                self._loading_status["elapsed"] = elapsed
                self._loading_status["status"] = "done"
                save_model_load_time(engine_name, elapsed)
                logger.info("TTS worker spawned in %.1fs", elapsed)
            except Exception as exc:
                elapsed = round(time.time() - self._loading_status["start_time"], 1)
                self._loading_status["elapsed"] = elapsed
                self._loading_status["status"] = "error"
                self._tts_error = str(exc)
                self._tts_engine = None
                self._tts_proxy = None
                logger.warning(
                    "TTS engine '%s' not available — install via Dashboard or: "
                    "dictare dependencies resolve\n  error: %s",
                    engine_name,
                    exc,
                )
        else:
            self._load_in_process(engine_name, save_model_load_time)

    def _load_in_process(
        self, engine_name: str, save_fn: Any = None,
    ) -> None:
        """Load a TTS engine in the main process (lightweight engines)."""
        try:
            from dictare.tts import get_cached_tts_engine

            self._tts_engine = get_cached_tts_engine(self._config.tts)
            if hasattr(self._tts_engine, "_get_model_path"):
                self._tts_engine._get_model_path()
            elapsed = round(time.time() - self._loading_status["start_time"], 1)
            self._loading_status["elapsed"] = elapsed
            self._loading_status["status"] = "done"
            if save_fn:
                save_fn(engine_name, elapsed)
            logger.debug("TTS engine loaded in-process in %.1fs", elapsed)
        except ValueError as exc:
            elapsed = round(time.time() - self._loading_status["start_time"], 1)
            self._loading_status["elapsed"] = elapsed
            self._loading_status["status"] = "error"
            self._tts_error = str(exc)
            logger.warning(
                "TTS engine '%s' not available — fix: dictare dependencies resolve",
                engine_name,
            )

    @staticmethod
    def kill_orphaned_workers() -> None:
        """Kill any orphaned TTS worker processes from a previous engine run."""
        import os
        import signal

        try:
            result = subprocess.run(
                ["pgrep", "-f", "dictare.tts.worker"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return  # No matching processes

            for line in result.stdout.strip().splitlines():
                pid = int(line.strip())
                if pid == os.getpid():
                    continue
                logger.info("Killing orphaned TTS worker (PID %d)", pid)
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        except OSError:
            pass  # Best-effort cleanup

    def _spawn_worker(self, http_server: Any) -> None:
        """Spawn a persistent TTS worker subprocess and create the proxy engine."""
        import os

        from dictare.tts.proxy import WorkerTTSEngine
        from dictare.tts.venv import get_venv_python, get_worker_pythonpath

        self.kill_orphaned_workers()

        token = self._auth_token
        port = http_server.port
        engine_name = self._config.tts.engine

        # Use venv python if the engine has an isolated venv, else sys.executable
        venv_python = get_venv_python(engine_name)
        python = venv_python or sys.executable

        cmd = [
            python, "-m", "dictare.tts.worker",
            "--url", f"http://127.0.0.1:{port}",
            "--token", token,
            "--engine", engine_name,
            "--language", self._config.tts.language,
            "--speed", str(self._config.tts.speed),
        ]
        if self._config.tts.voice:
            cmd.extend(["--voice", self._config.tts.voice])

        # Build env for worker subprocess
        env = {**os.environ, "COQUI_TOS_AGREED": "1"}
        if venv_python:
            # When using venv python, inject PYTHONPATH so worker can import
            # dictare + openvip (may be in different source trees for dev installs)
            env["PYTHONPATH"] = get_worker_pythonpath()

        logger.info("Spawning TTS worker: %s", " ".join(cmd))
        self._tts_worker_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Create proxy engine — it will wait for worker to connect
        proxy = WorkerTTSEngine(http_server)
        self._tts_proxy = proxy
        self._tts_engine = proxy

        # Wait for worker to connect, polling for early crash every 0.5s
        deadline = time.monotonic() + _TTS_WORKER_CONNECT_TIMEOUT
        while not http_server.is_tts_connected():
            # Check if process died (fail fast instead of waiting 120s)
            if self._tts_worker_process.poll() is not None:
                stderr = self._tts_worker_process.stderr
                err_output = stderr.read().decode() if stderr else ""
                raise RuntimeError(
                    f"TTS worker exited with code {self._tts_worker_process.returncode}: "
                    f"{err_output[:500]}"
                )
            if time.monotonic() > deadline:
                raise RuntimeError("TTS worker failed to connect within 120s")
            http_server.wait_tts_connected(timeout=0.5)

        logger.info("TTS worker connected")

    # ------------------------------------------------------------------
    # Speech
    # ------------------------------------------------------------------

    def speak_text(self, text: str) -> None:
        """Speak text using the pre-loaded TTS engine, optionally pausing the mic.

        Args:
            text: Text to speak.
        """
        if self._tts_error:
            logger.warning("speak_text(%r): TTS failed to load: %s", text, self._tts_error)
            return
        if self._tts_engine is None:
            logger.warning("speak_text(%r): TTS engine not loaded", text)
            return

        from dictare.audio.beep import get_sound_for_event

        enabled, _ = get_sound_for_event(self._config.audio, "agent_announce")
        if not enabled:
            return

        from dictare.audio.beep import play_audio

        tts = self._tts_engine
        logger.info("TTS: %r", text)

        def _do_tts() -> None:
            try:
                ok = tts.speak(text)
                if not ok:
                    logger.warning("TTS speak(%r) returned False", text)
            except Exception:
                logger.warning("TTS speak failed for %r", text, exc_info=True)

        pause = not self._config.audio.headphones_mode
        play_audio(_do_tts, pause_mic=pause, controller=self._controller)

    def speak_agent(self, agent_name: str) -> None:
        """Speak agent name using OS TTS.

        Announces "{agent_prefix} {agent_name}" (e.g., "agent claude").
        The prefix is configurable via ~/.config/dictare/tts_phrases.json.

        Args:
            agent_name: Name of the agent to announce.
        """
        phrases = self._load_tts_phrases()
        agent_prefix = phrases.get("agent", "agent")
        display_name = agent_name.strip("_")
        self.speak_text(f"{agent_prefix} {display_name}")

    def handle_speech(self, body: dict) -> dict:
        """Handle a speech (TTS) request.

        Uses the running TTS worker. Accepts ``language`` and ``speed``
        overrides for future per-request support.

        If ``engine`` is specified and differs from the configured engine,
        returns an error — switching engines requires a config change.

        Args:
            body: Request body with ``text`` (required) and optional
                ``engine``, ``language``, ``speed``.

        Returns:
            Response dict with status and duration.

        Raises:
            ValueError: If requested engine differs from configured engine.
        """
        text = body.get("text", "")
        if not text:
            return {"status": "error", "error": "No text provided"}

        # Reject engine mismatch early
        requested_engine = body.get("engine")
        if requested_engine and requested_engine != self._config.tts.engine:
            raise ValueError(
                f"Requested engine '{requested_engine}' is not the configured "
                f"engine ('{self._config.tts.engine}'). "
                f"Change it in Settings → Speech."
            )

        if self._tts_engine is None:
            error = self._tts_error or "TTS engine not loaded"
            return {"status": "error", "error": error}

        tts = self._tts_engine

        # Per-request overrides (optional, protocol fields)
        voice = body.get("voice") or None
        language = body.get("language") or None
        speak_kwargs: dict[str, str] = {}
        if voice:
            speak_kwargs["voice"] = voice
        if language:
            speak_kwargs["language"] = language

        # Mic-pausing via play counter: mic stays paused while any play is active.
        # 0→1 sends PlayStarted, N→0 sends PlayCompleted.
        pause = not self._config.audio.headphones_mode

        start = time.time()

        if pause:
            self._play_start()
        try:
            ok = tts.speak(text, **speak_kwargs)
        finally:
            if pause:
                self._play_end()

        duration_ms = int((time.time() - start) * 1000)

        if not ok:
            return {"status": "error", "error": "TTS engine failed to speak"}

        return {"openvip": "1.0", "status": "ok", "duration_ms": duration_ms}

    def list_voices(self) -> list[str]:
        """Return available voices for the configured TTS engine."""
        from dictare.tts.venv import VENV_ENGINES

        engine_name = self._config.tts.engine

        # Worker-based engines: query via venv subprocess
        if engine_name in VENV_ENGINES:
            return self._list_voices_via_venv(engine_name)

        # Direct engines: call list_voices() on the loaded engine
        if self._tts_engine is not None:
            return self._tts_engine.list_voices()

        return []

    @staticmethod
    def _list_voices_via_venv(engine_name: str) -> list[str]:
        """List voices by running a script in the engine's venv."""
        from dictare.tts.venv import get_venv_python

        venv_python = get_venv_python(engine_name)
        if venv_python is None:
            return []

        if engine_name == "kokoro":
            script = (
                "from kokoro_onnx import Kokoro; from pathlib import Path; "
                "d = Path.home() / '.local/share/dictare/models/kokoro'; "
                "k = Kokoro(str(d / 'model.onnx'), str(d / 'voices.bin')); "
                "print('\\n'.join(sorted(k.voices.keys())))"
            )
        else:
            return []

        try:
            result = subprocess.run(
                [venv_python, "-c", script],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return []
            return [v for v in result.stdout.strip().splitlines() if v]
        except (OSError, subprocess.TimeoutExpired):
            return []

    # ------------------------------------------------------------------
    # Mic pausing (play counter, thread-safe)
    # ------------------------------------------------------------------

    def _play_start(self) -> None:
        """Increment active play count. Pauses mic on first play (0→1)."""
        with self._play_lock:
            self._active_plays += 1
            first = self._active_plays == 1

        if first and self._controller is not None:
            from dictare.core.fsm import AppState, PlayStarted

            if self._controller.state != AppState.OFF:
                try:
                    self._controller.send(PlayStarted(text="", source="tts"))
                except Exception:
                    pass

    def _play_end(self) -> None:
        """Decrement active play count. Resumes mic when last play ends (N→0)."""
        with self._play_lock:
            self._active_plays = max(0, self._active_plays - 1)
            last = self._active_plays == 0

        if last and self._controller is not None:
            from dictare.core.fsm import PlayCompleted

            try:
                self._controller.send(PlayCompleted(source="tts"))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_tts_phrases() -> dict:
        """Load TTS phrases from config file or use defaults."""
        from pathlib import Path

        default_phrases = {
            "agent": "agent",
        }

        phrases_path = Path.home() / ".config" / "dictare" / "tts_phrases.json"
        if phrases_path.exists():
            try:
                with open(phrases_path) as f:
                    custom = json.load(f)
                return {**default_phrases, **custom}
            except (OSError, json.JSONDecodeError, ValueError):
                pass

        return default_phrases

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop_speaking(self) -> bool:
        """Interrupt the currently playing audio.

        For worker-based engines (kokoro/piper/etc.): sends SIGUSR2 to the
        worker subprocess, which kills the audio player subprocess.

        For in-process engines (say/espeak): calls stop_audio_native() directly.

        Returns:
            True if a stop signal was delivered, False if nothing to stop.
        """
        import sys

        if self._tts_worker_process is not None:
            # Worker-based engine: signal the worker
            if sys.platform == "win32":
                return False  # SIGUSR2 not available on Windows
            import os
            import signal as _signal

            pid = self._tts_worker_process.pid
            try:
                os.kill(pid, _signal.SIGUSR2)
                logger.info("Sent SIGUSR2 to TTS worker (PID %d)", pid)
                return True
            except (ProcessLookupError, OSError):
                return False
        else:
            # In-process engine: kill the audio subprocess directly
            from dictare.tts.base import stop_audio_native

            stopped = stop_audio_native()
            if stopped:
                logger.info("Stopped in-process audio playback")
            return stopped

    def complete_tts(self, message_id: str, *, ok: bool, duration_ms: int = 0) -> None:
        """Signal that the worker finished processing a TTS message."""
        if self._tts_proxy is not None:
            self._tts_proxy.complete(message_id, ok=ok, duration_ms=duration_ms)

    def stop(self) -> None:
        """Stop the TTS worker subprocess if running."""
        if self._tts_worker_process is not None:
            logger.info("Stopping TTS worker (PID %d)", self._tts_worker_process.pid)
            self._tts_worker_process.terminate()
            try:
                self._tts_worker_process.wait(timeout=_TTS_WORKER_STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                self._tts_worker_process.kill()
            self._tts_worker_process = None
