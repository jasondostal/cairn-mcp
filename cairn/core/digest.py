"""DigestWorker — background thread that processes event batches into LLM digests."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cairn.core.constants import DIGEST_MAX_EVENTS_PER_BATCH, DIGEST_POLL_INTERVAL

if TYPE_CHECKING:
    from cairn.config import LLMCapabilities
    from cairn.llm.interface import LLMInterface
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class DigestWorker:
    """Background worker that polls for undigested event batches and processes them.

    Runs as a daemon thread. Polls session_events for rows where digest IS NULL,
    processes one at a time via LLM, and updates the row with the digest text.

    Graceful degradation: if LLM fails, the batch stays undigested and retries
    on the next poll cycle (with backoff on repeated errors).
    """

    def __init__(
        self, db: Database, *,
        llm: LLMInterface | None = None,
        capabilities: LLMCapabilities | None = None,
    ):
        self.db = db
        self.llm = llm
        self.capabilities = capabilities
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def can_digest(self) -> bool:
        """Check if digestion is possible (LLM available + capability enabled)."""
        return (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.event_digest
        )

    def start(self) -> None:
        """Start the background digest thread."""
        if not self.can_digest():
            logger.info("DigestWorker: skipping start (LLM unavailable or event_digest disabled)")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="DigestWorker")
        self._thread.start()
        logger.info("DigestWorker: started")

    def stop(self) -> None:
        """Signal the worker to stop and wait for it to finish."""
        if self._thread is None:
            return

        self._stop_event.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.warning("DigestWorker: thread did not stop within timeout")
        else:
            logger.info("DigestWorker: stopped")
        self._thread = None

    def _run_loop(self) -> None:
        """Main loop: poll for undigested batches, process one at a time."""
        poll_interval = DIGEST_POLL_INTERVAL

        while not self._stop_event.is_set():
            try:
                processed = self._process_one_batch()
                if processed:
                    poll_interval = DIGEST_POLL_INTERVAL  # reset backoff
                else:
                    # Nothing to process — wait before next poll
                    self._stop_event.wait(timeout=poll_interval)
            except Exception:
                logger.warning("DigestWorker: error in poll cycle, backing off", exc_info=True)
                poll_interval = min(poll_interval * 3, 60.0)  # backoff, cap at 60s
                self._stop_event.wait(timeout=poll_interval)

    def _process_one_batch(self) -> bool:
        """Find and digest the oldest undigested batch.

        Returns:
            True if a batch was processed, False if queue is empty.
        """
        from cairn.llm.prompts import build_event_digest_messages

        # SELECT oldest undigested row with project name
        row = self.db.execute_one(
            """
            SELECT se.id, se.project_id, se.session_name, se.batch_number,
                   se.raw_events, se.event_count, p.name as project
            FROM session_events se
            LEFT JOIN projects p ON se.project_id = p.id
            WHERE se.digest IS NULL
            ORDER BY se.created_at ASC
            LIMIT 1
            """,
            (),
        )

        if not row:
            return False

        batch_id = row["id"]
        project = row["project"] or "unknown"
        session_name = row["session_name"]
        batch_number = row["batch_number"]
        raw_events = row["raw_events"]

        # Cap events sent to LLM
        events = raw_events if isinstance(raw_events, list) else []
        if len(events) > DIGEST_MAX_EVENTS_PER_BATCH:
            events = events[:DIGEST_MAX_EVENTS_PER_BATCH]

        logger.info(
            "DigestWorker: processing batch %d (session=%s, batch=%d, events=%d)",
            batch_id, session_name, batch_number, len(events),
        )

        messages = build_event_digest_messages(events, project, session_name, batch_number)
        digest_text = self.llm.generate(messages, max_tokens=512)

        if not digest_text or not digest_text.strip():
            logger.warning("DigestWorker: LLM returned empty digest for batch %d", batch_id)
            return False

        now = datetime.now(timezone.utc)
        self.db.execute(
            "UPDATE session_events SET digest = %s, digested_at = %s WHERE id = %s",
            (digest_text.strip(), now, batch_id),
        )
        self.db.commit()

        logger.info("DigestWorker: digested batch %d → %d chars", batch_id, len(digest_text.strip()))
        return True

    def digest_immediate(self, batch_id: int) -> str | None:
        """Synchronous digest path for testing — process a specific batch by ID.

        Returns:
            The digest text, or None if batch not found or LLM failed.
        """
        from cairn.llm.prompts import build_event_digest_messages

        if not self.can_digest():
            return None

        row = self.db.execute_one(
            """
            SELECT se.id, se.project_id, se.session_name, se.batch_number,
                   se.raw_events, se.event_count, p.name as project
            FROM session_events se
            LEFT JOIN projects p ON se.project_id = p.id
            WHERE se.id = %s
            """,
            (batch_id,),
        )

        if not row:
            return None

        events = row["raw_events"] if isinstance(row["raw_events"], list) else []
        if len(events) > DIGEST_MAX_EVENTS_PER_BATCH:
            events = events[:DIGEST_MAX_EVENTS_PER_BATCH]

        messages = build_event_digest_messages(
            events, row["project"] or "unknown", row["session_name"], row["batch_number"],
        )

        try:
            digest_text = self.llm.generate(messages, max_tokens=512)
        except Exception:
            logger.warning("DigestWorker: immediate digest failed for batch %d", batch_id, exc_info=True)
            return None

        if not digest_text or not digest_text.strip():
            return None

        now = datetime.now(timezone.utc)
        self.db.execute(
            "UPDATE session_events SET digest = %s, digested_at = %s WHERE id = %s",
            (digest_text.strip(), now, batch_id),
        )
        self.db.commit()

        return digest_text.strip()
