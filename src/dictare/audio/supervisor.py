"""Single-owner executor for PortAudio lifecycle operations."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from queue import Queue
from typing import Any

from dictare.audio.capture import PortAudioCallTimeoutError

logger = logging.getLogger(__name__)


class AudioControlPoisonedError(RuntimeError):
    """Raised when native audio timed out and this process cannot be reused."""


class AudioControlClosedError(RuntimeError):
    """Raised when work is submitted after the control executor has closed."""


@dataclass
class _Request:
    label: str
    action: Callable[[], Any]
    coalesce_key: str | None = None
    done: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


class AudioControl:
    """Serialize all native audio lifecycle calls on one control thread.

    A native timeout is terminal for the current process: the executor rejects
    every later request and asks the outer engine supervisor to replace it.
    """

    def __init__(self, on_poisoned: Callable[[str], None] | None = None) -> None:
        self._on_poisoned = on_poisoned
        self._queue: Queue[_Request | None] = Queue()
        self._lock = threading.Lock()
        self._queued_keys: set[str] = set()
        self._poisoned_reason: str | None = None
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="dictare-audio-control",
        )
        self._thread.start()

    @property
    def poisoned(self) -> bool:
        """Whether a native timeout made this process unsafe for more audio work."""
        with self._lock:
            return self._poisoned_reason is not None

    @property
    def poisoned_reason(self) -> str | None:
        """Return the first native timeout description, if any."""
        with self._lock:
            return self._poisoned_reason

    @property
    def owner_thread_id(self) -> int | None:
        """Thread identifier used by tests and diagnostics."""
        return self._thread.ident

    def execute(self, label: str, action: Callable[[], Any]) -> Any:
        """Run *action* on the owner thread and return its result."""
        if threading.current_thread() is self._thread:
            return self._execute_owned(label, action)

        request = _Request(label=label, action=action)
        self._enqueue(request)
        request.done.wait()
        if request.error is not None:
            raise request.error
        return request.result

    def request(
        self,
        label: str,
        action: Callable[[], Any],
        *,
        coalesce_key: str,
    ) -> bool:
        """Queue fire-and-forget work, dropping duplicate queued requests."""
        request = _Request(label=label, action=action, coalesce_key=coalesce_key)
        with self._lock:
            self._check_available_locked()
            if coalesce_key in self._queued_keys:
                return False
            self._queued_keys.add(coalesce_key)
            self._queue.put(request)
        return True

    def barrier(self) -> None:
        """Wait until all work queued before this call has completed."""
        self.execute("barrier", lambda: None)

    def shutdown(self) -> None:
        """Reject future work and stop the owner thread without native cleanup."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._queue.put(None)
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)

    def _enqueue(self, request: _Request) -> None:
        with self._lock:
            self._check_available_locked()
            self._queue.put(request)

    def _check_available_locked(self) -> None:
        if self._poisoned_reason is not None:
            raise AudioControlPoisonedError(self._poisoned_reason)
        if self._closed:
            raise AudioControlClosedError("audio control is closed")

    def _run(self) -> None:
        while True:
            request = self._queue.get()
            if request is None:
                return
            if request.coalesce_key is not None:
                # Remove before execution so events arriving during a recovery
                # collapse into at most one follow-up recovery.
                with self._lock:
                    self._queued_keys.discard(request.coalesce_key)
            try:
                request.result = self._execute_owned(request.label, request.action)
            except BaseException as exc:  # noqa: BLE001 - delivered to submitter
                request.error = exc
                if request.coalesce_key is not None:
                    logger.error(
                        "Asynchronous audio control request failed: %s",
                        request.label,
                        exc_info=True,
                    )
            finally:
                request.done.set()

    def _execute_owned(self, label: str, action: Callable[[], Any]) -> Any:
        with self._lock:
            self._check_available_locked()
        try:
            return action()
        except PortAudioCallTimeoutError as exc:
            reason = f"{label}: {exc}"
            self._poison(reason)
            raise AudioControlPoisonedError(reason) from exc

    def _poison(self, reason: str) -> None:
        callback: Callable[[str], None] | None = None
        with self._lock:
            if self._poisoned_reason is not None:
                return
            self._poisoned_reason = reason
            callback = self._on_poisoned
        logger.critical("Audio control poisoned: %s", reason)
        if callback is not None:
            try:
                callback(reason)
            except Exception:
                logger.exception("Audio poison callback failed")
