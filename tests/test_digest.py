"""Tests for DigestWorker — event batch digestion."""

import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from cairn.config import LLMCapabilities
from cairn.core.digest import DigestWorker


def _make_db():
    """Create a mock Database."""
    db = MagicMock()
    return db


def _make_batch_row(batch_id=1, project="test-project", session_name="test-session",
                    batch_number=0, event_count=5):
    """Create a mock session_events row."""
    return {
        "id": batch_id,
        "project_id": 1,
        "session_name": session_name,
        "batch_number": batch_number,
        "raw_events": [
            {"ts": "2026-02-09T12:00:00Z", "tool_name": "Read", "tool_input": {"file_path": "/src/main.py"}},
            {"ts": "2026-02-09T12:01:00Z", "tool_name": "Edit", "tool_input": {"file_path": "/src/main.py"}},
            {"ts": "2026-02-09T12:02:00Z", "tool_name": "Bash", "tool_input": {"command": "pytest"}},
            {"ts": "2026-02-09T12:03:00Z", "tool_name": "Read", "tool_input": {"file_path": "/src/utils.py"}},
            {"ts": "2026-02-09T12:04:00Z", "tool_name": "Grep", "tool_input": {"pattern": "def main"}},
        ],
        "event_count": event_count,
        "project": project,
    }


class TestDigestWorkerCanDigest:
    """Tests for capability matrix."""

    def test_can_digest_with_llm_and_capability(self):
        """Worker can digest when LLM is available and capability enabled."""
        db = _make_db()
        llm = MagicMock()
        caps = LLMCapabilities(event_digest=True)
        worker = DigestWorker(db, llm=llm, capabilities=caps)
        assert worker.can_digest() is True

    def test_cannot_digest_without_llm(self):
        """Worker cannot digest without LLM."""
        db = _make_db()
        caps = LLMCapabilities(event_digest=True)
        worker = DigestWorker(db, llm=None, capabilities=caps)
        assert worker.can_digest() is False

    def test_cannot_digest_with_capability_disabled(self):
        """Worker cannot digest when event_digest is disabled."""
        db = _make_db()
        llm = MagicMock()
        caps = LLMCapabilities(event_digest=False)
        worker = DigestWorker(db, llm=llm, capabilities=caps)
        assert worker.can_digest() is False

    def test_cannot_digest_without_capabilities(self):
        """Worker cannot digest without capabilities object."""
        db = _make_db()
        llm = MagicMock()
        worker = DigestWorker(db, llm=llm, capabilities=None)
        assert worker.can_digest() is False


class TestProcessOneBatch:
    """Tests for _process_one_batch()."""

    def test_processes_batch_successfully(self):
        """Processing a batch calls LLM and updates the row."""
        db = _make_db()
        llm = MagicMock()
        llm.generate.return_value = "Explored main.py, edited it, ran tests, then checked utils.py for a function definition."
        caps = LLMCapabilities(event_digest=True)

        batch_row = _make_batch_row()
        db.execute_one.return_value = batch_row

        worker = DigestWorker(db, llm=llm, capabilities=caps)
        result = worker._process_one_batch()

        assert result is True
        llm.generate.assert_called_once()
        # Verify UPDATE was called with digest text
        update_call = db.execute.call_args
        assert "UPDATE session_events SET digest" in update_call[0][0]
        db.commit.assert_called_once()

    def test_empty_queue_returns_false(self):
        """When no undigested batches exist, returns False."""
        db = _make_db()
        llm = MagicMock()
        caps = LLMCapabilities(event_digest=True)

        db.execute_one.return_value = None  # no undigested rows

        worker = DigestWorker(db, llm=llm, capabilities=caps)
        result = worker._process_one_batch()

        assert result is False
        llm.generate.assert_not_called()

    def test_llm_failure_leaves_batch_undigested(self):
        """If LLM raises an exception, the batch is not marked as digested."""
        db = _make_db()
        llm = MagicMock()
        llm.generate.side_effect = RuntimeError("LLM connection failed")
        caps = LLMCapabilities(event_digest=True)

        batch_row = _make_batch_row()
        db.execute_one.return_value = batch_row

        worker = DigestWorker(db, llm=llm, capabilities=caps)

        # _process_one_batch should propagate exception (run_loop catches it)
        try:
            worker._process_one_batch()
        except RuntimeError:
            pass

        # No UPDATE or commit should have happened
        db.commit.assert_not_called()

    def test_empty_llm_response_returns_false(self):
        """If LLM returns empty string, batch stays undigested."""
        db = _make_db()
        llm = MagicMock()
        llm.generate.return_value = "   "  # whitespace only
        caps = LLMCapabilities(event_digest=True)

        batch_row = _make_batch_row()
        db.execute_one.return_value = batch_row

        worker = DigestWorker(db, llm=llm, capabilities=caps)
        result = worker._process_one_batch()

        assert result is False
        db.commit.assert_not_called()


class TestDigestWorkerLifecycle:
    """Tests for start/stop lifecycle."""

    def test_start_creates_daemon_thread(self):
        """Starting the worker creates a daemon thread."""
        db = _make_db()
        llm = MagicMock()
        caps = LLMCapabilities(event_digest=True)

        worker = DigestWorker(db, llm=llm, capabilities=caps)

        # Mock _run_loop to avoid actual polling
        worker._run_loop = MagicMock()
        worker.start()

        assert worker._thread is not None
        assert worker._thread.daemon is True
        assert worker._thread.name == "DigestWorker"

        worker.stop()
        assert worker._thread is None

    def test_stop_safe_when_not_started(self):
        """Stopping a worker that was never started is safe."""
        db = _make_db()
        worker = DigestWorker(db)
        worker.stop()  # should not raise

    def test_start_skips_when_cannot_digest(self):
        """Worker does not start thread if digestion is not possible."""
        db = _make_db()
        worker = DigestWorker(db, llm=None)  # no LLM
        worker.start()
        assert worker._thread is None


class TestDigestImmediate:
    """Tests for synchronous digest_immediate()."""

    def test_immediate_digests_specific_batch(self):
        """digest_immediate processes a specific batch by ID."""
        db = _make_db()
        llm = MagicMock()
        llm.generate.return_value = "Investigated main.py and ran the test suite."
        caps = LLMCapabilities(event_digest=True)

        batch_row = _make_batch_row(batch_id=42)
        db.execute_one.return_value = batch_row

        worker = DigestWorker(db, llm=llm, capabilities=caps)
        result = worker.digest_immediate(42)

        assert result == "Investigated main.py and ran the test suite."
        llm.generate.assert_called_once()
        db.commit.assert_called_once()

    def test_immediate_returns_none_when_cannot_digest(self):
        """digest_immediate returns None when digestion is not possible."""
        db = _make_db()
        worker = DigestWorker(db, llm=None)
        result = worker.digest_immediate(1)
        assert result is None

    def test_immediate_returns_none_for_missing_batch(self):
        """digest_immediate returns None when batch ID doesn't exist."""
        db = _make_db()
        llm = MagicMock()
        caps = LLMCapabilities(event_digest=True)
        db.execute_one.return_value = None

        worker = DigestWorker(db, llm=llm, capabilities=caps)
        result = worker.digest_immediate(999)

        assert result is None
        llm.generate.assert_not_called()

    def test_immediate_handles_llm_failure(self):
        """digest_immediate returns None on LLM failure."""
        db = _make_db()
        llm = MagicMock()
        llm.generate.side_effect = RuntimeError("LLM down")
        caps = LLMCapabilities(event_digest=True)

        batch_row = _make_batch_row()
        db.execute_one.return_value = batch_row

        worker = DigestWorker(db, llm=llm, capabilities=caps)
        result = worker.digest_immediate(1)

        assert result is None
        db.commit.assert_not_called()
