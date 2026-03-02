"""Tests for race conditions.

These tests verify that concurrent operations don't lose data or corrupt state.
This is the most critical test file - race conditions have been the primary
source of bugs in dictare.
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from dictare.core.fsm import AppState, StateManager

pytestmark = pytest.mark.slow

class TestMuxFileReaderRaceConditions:
    """Test race conditions in agent mux file reading.

    The _read_from_file function must not lose data when:
    - Writer is writing rapidly
    - Writer writes partial lines (mid-write reads)
    - Multiple rapid writes happen in sequence
    """

    def _simulate_reader(
        self,
        filepath: str,
        stop_event: threading.Event,
        results: list,
        timeout: float = 5.0,
    ) -> None:
        """Simulate the mux file reader logic with line buffering.

        This mirrors the fix in mux.py: buffer incomplete lines.
        """
        line_buffer = ""
        start_time = time.time()

        with open(filepath) as f:
            f.seek(0, os.SEEK_END)

            while not stop_event.is_set():
                if time.time() - start_time > timeout:
                    break

                chunk = f.readline()
                if chunk:
                    line_buffer += chunk

                    # Only process complete lines
                    if not line_buffer.endswith("\n"):
                        time.sleep(0.001)
                        continue

                    line = line_buffer.strip()
                    line_buffer = ""

                    if not line:
                        continue

                    try:
                        msg = json.loads(line)
                        results.append(msg)
                    except json.JSONDecodeError:
                        # This should NOT happen with complete lines
                        results.append({"error": "JSONDecodeError", "line": line})
                else:
                    time.sleep(0.01)
                    f.seek(f.tell())

    def test_rapid_writes_no_data_loss(self) -> None:
        """Rapid sequential writes should not lose any messages."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            filepath = f.name

        try:
            results = []
            stop_event = threading.Event()
            num_messages = 100

            # Start reader
            reader_thread = threading.Thread(
                target=self._simulate_reader,
                args=(filepath, stop_event, results),
            )
            reader_thread.start()

            # Give reader time to start
            time.sleep(0.05)

            # Writer: write messages rapidly
            for i in range(num_messages):
                with open(filepath, "a") as f:
                    f.write(json.dumps({"text": f"message_{i}"}) + "\n")
                    f.flush()
                time.sleep(0.001)  # Very fast writes

            # Wait for reader to catch up (poll instead of fixed sleep)
            deadline = time.time() + 5.0
            while len([r for r in results if "error" not in r]) < num_messages and time.time() < deadline:
                time.sleep(0.001)
            stop_event.set()
            reader_thread.join(timeout=2.0)

            # Verify NO data loss
            valid_results = [r for r in results if "error" not in r]
            assert len(valid_results) == num_messages, (
                f"Expected {num_messages} messages, got {len(valid_results)}. "
                f"Lost {num_messages - len(valid_results)} messages!"
            )

            # Verify order preserved
            for i, msg in enumerate(valid_results):
                assert msg["text"] == f"message_{i}", f"Wrong order at index {i}"

        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_burst_writes_no_data_loss(self) -> None:
        """Burst of writes (no sleep between) should not lose data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            filepath = f.name

        try:
            results = []
            stop_event = threading.Event()
            num_messages = 50

            reader_thread = threading.Thread(
                target=self._simulate_reader,
                args=(filepath, stop_event, results),
            )
            reader_thread.start()
            time.sleep(0.05)

            # Write ALL messages as fast as possible (burst)
            with open(filepath, "a") as f:
                for i in range(num_messages):
                    f.write(json.dumps({"text": f"burst_{i}"}) + "\n")
                f.flush()

            deadline = time.time() + 5.0
            while len([r for r in results if "error" not in r]) < num_messages and time.time() < deadline:
                time.sleep(0.001)
            stop_event.set()
            reader_thread.join(timeout=2.0)

            valid_results = [r for r in results if "error" not in r]
            assert len(valid_results) == num_messages

        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_multiline_atomic_writes_no_loss(self) -> None:
        """Atomic writes of multiple lines should not lose data.

        This tests the pattern used by FileInjector when auto_submit=false:
        writing text + newline in a single write() call.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            filepath = f.name

        try:
            results = []
            stop_event = threading.Event()
            num_pairs = 30

            reader_thread = threading.Thread(
                target=self._simulate_reader,
                args=(filepath, stop_event, results),
            )
            reader_thread.start()
            time.sleep(0.05)

            # Write pairs atomically (text + newline in single write)
            for i in range(num_pairs):
                output = (
                    json.dumps({"text": f"phrase_{i}"}) + "\n" +
                    json.dumps({"text": "\n"}) + "\n"
                )
                with open(filepath, "a") as f:
                    f.write(output)  # Single write for both lines
                    f.flush()
                time.sleep(0.005)

            expected = num_pairs * 2
            deadline = time.time() + 5.0
            while len([r for r in results if "error" not in r]) < expected and time.time() < deadline:
                time.sleep(0.001)
            stop_event.set()
            reader_thread.join(timeout=2.0)

            valid_results = [r for r in results if "error" not in r]
            # Should have num_pairs * 2 messages (text + newline for each)
            assert len(valid_results) == num_pairs * 2, (
                f"Expected {num_pairs * 2} messages, got {len(valid_results)}"
            )

        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_concurrent_writers_no_corruption(self) -> None:
        """Multiple writers should not corrupt the reader's data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            filepath = f.name

        try:
            results = []
            stop_event = threading.Event()
            num_writers = 5
            messages_per_writer = 20

            reader_thread = threading.Thread(
                target=self._simulate_reader,
                args=(filepath, stop_event, results, 10.0),
            )
            reader_thread.start()
            time.sleep(0.05)

            def writer(writer_id: int):
                for i in range(messages_per_writer):
                    with open(filepath, "a") as f:
                        f.write(json.dumps({"writer": writer_id, "seq": i}) + "\n")
                        f.flush()
                    time.sleep(0.002)

            writer_threads = [
                threading.Thread(target=writer, args=(w,))
                for w in range(num_writers)
            ]
            for t in writer_threads:
                t.start()
            for t in writer_threads:
                t.join()

            expected_total = num_writers * messages_per_writer
            deadline = time.time() + 5.0
            while len([r for r in results if "error" not in r]) < expected_total and time.time() < deadline:
                time.sleep(0.001)
            stop_event.set()
            reader_thread.join(timeout=2.0)

            valid_results = [r for r in results if "error" not in r]
            assert len(valid_results) == expected_total, (
                f"Expected {expected_total} messages, got {len(valid_results)}"
            )

            # Verify each writer's messages are complete
            for writer_id in range(num_writers):
                writer_msgs = [r for r in valid_results if r.get("writer") == writer_id]
                assert len(writer_msgs) == messages_per_writer, (
                    f"Writer {writer_id} lost messages"
                )

        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_no_json_decode_errors_with_buffering(self) -> None:
        """With proper buffering, JSONDecodeError should never occur."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            filepath = f.name

        try:
            results = []
            stop_event = threading.Event()

            reader_thread = threading.Thread(
                target=self._simulate_reader,
                args=(filepath, stop_event, results),
            )
            reader_thread.start()
            time.sleep(0.05)

            # Write with various delays to stress the reader
            for i in range(50):
                with open(filepath, "a") as f:
                    f.write(json.dumps({"index": i, "data": "x" * 100}) + "\n")
                    f.flush()
                # Variable delays
                time.sleep(0.001 * (i % 5))

            deadline = time.time() + 5.0
            while len(results) < 50 and time.time() < deadline:
                time.sleep(0.001)
            stop_event.set()
            reader_thread.join(timeout=2.0)

            # Check for any JSON decode errors
            errors = [r for r in results if "error" in r]
            assert len(errors) == 0, f"Got {len(errors)} JSON decode errors: {errors}"

        finally:
            Path(filepath).unlink(missing_ok=True)

class TestStateManagerRaceConditions:
    """Additional stress tests for state machine race conditions.

    Note: Basic thread safety tests are in test_state.py.
    These are more aggressive stress tests.
    """

    def test_rapid_toggle_stress(self) -> None:
        """Rapid state toggles should not corrupt state."""
        sm = StateManager(initial_state=AppState.LISTENING)
        errors = []
        iterations = 1000

        def toggle():
            for _ in range(iterations):
                try:
                    # Try to go through a workflow
                    if sm.try_transition(AppState.RECORDING):
                        sm.try_transition(AppState.TRANSCRIBING)
                        sm.try_transition(AppState.LISTENING)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=toggle) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert sm.state in AppState

    def test_reset_during_workflow(self) -> None:
        """Reset during workflow should not corrupt state."""
        sm = StateManager(initial_state=AppState.LISTENING)
        errors = []

        def workflow():
            for _ in range(100):
                try:
                    sm.try_transition(AppState.RECORDING)
                    time.sleep(0.001)
                    sm.try_transition(AppState.TRANSCRIBING)
                    time.sleep(0.001)
                    sm.try_transition(AppState.LISTENING)
                except Exception as e:
                    errors.append(e)

        def resetter():
            for _ in range(100):
                sm.reset_to_listening()
                time.sleep(0.002)

        t1 = threading.Thread(target=workflow)
        t2 = threading.Thread(target=resetter)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0
        # Final state should be valid (likely LISTENING from reset)
        assert sm.state in AppState

