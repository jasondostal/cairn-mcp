"""EventDispatcher — background worker that processes event dispatch records.

Polls the event_dispatches table for pending/failed records, resolves the
handler by name via EventBus, executes it, and tracks success/failure with
exponential backoff retry.

Follows the same thread lifecycle pattern as UsageTracker and RollupWorker.
"""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class EventDispatcher:
    """Background thread that reliably delivers events to registered handlers."""

    POLL_INTERVAL = 2.0     # seconds between polls
    BATCH_SIZE = 50         # max dispatches per poll cycle
    MAX_ATTEMPTS = 5        # give up after this many tries
    BACKOFF_BASE = 10       # seconds; actual = base * 2^attempts

    def __init__(self, db: Database, event_bus: EventBus):
        self.db = db
        self.event_bus = event_bus
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the dispatch loop in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="EventDispatcher",
        )
        self._thread.start()
        logger.info("EventDispatcher: started")

    def stop(self) -> None:
        """Signal stop and wait for the thread to finish."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.warning("EventDispatcher: thread did not stop within timeout")
        else:
            logger.info("EventDispatcher: stopped")
        self._thread = None

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception:
                logger.warning("EventDispatcher: poll cycle failed", exc_info=True)
            self._stop_event.wait(timeout=self.POLL_INTERVAL)
        # Final drain on shutdown
        try:
            self._poll()
        except Exception:
            pass

    def _poll(self) -> None:
        """Fetch pending dispatches and execute handlers."""
        rows = self.db.execute(
            """
            SELECT ed.id, ed.event_id, ed.handler, ed.attempts,
                   e.event_type, e.payload, e.project_id, e.work_item_id,
                   e.session_name
            FROM event_dispatches ed
            JOIN events e ON e.id = ed.event_id
            WHERE ed.status IN ('pending', 'failed')
              AND ed.next_retry <= NOW()
              AND ed.attempts < %s
            ORDER BY e.id ASC
            LIMIT %s
            """,
            (self.MAX_ATTEMPTS, self.BATCH_SIZE),
        )

        if not rows:
            # Release the connection so the next poll gets a fresh transaction.
            # Without this, the thread-local connection stays checked out in an
            # open transaction indefinitely (autocommit=False).
            self.db.rollback()
            return

        processed = 0
        for row in rows:
            handler_fn = self.event_bus.get_handler(row["handler"])
            if handler_fn is None:
                self._mark_exhausted(row["id"], f"handler '{row['handler']}' not found")
                processed += 1
                continue

            event = {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "payload": row["payload"] or {},
                "project_id": row["project_id"],
                "work_item_id": row["work_item_id"],
                "session_name": row["session_name"],
            }

            try:
                handler_fn(event)
                self._mark_success(row["id"])
                processed += 1
            except Exception:
                tb = traceback.format_exc()
                self._mark_failed(row["id"], row["attempts"], tb)
                processed += 1
                logger.warning(
                    "EventDispatcher: handler '%s' failed for event %d (attempt %d)",
                    row["handler"], row["event_id"], row["attempts"] + 1,
                )

        if processed:
            logger.info("EventDispatcher: processed %d dispatches", processed)

    # ------------------------------------------------------------------
    # Status updates
    # ------------------------------------------------------------------

    def _mark_success(self, dispatch_id: int) -> None:
        self.db.execute(
            """
            UPDATE event_dispatches
            SET status = 'success', completed_at = NOW()
            WHERE id = %s
            """,
            (dispatch_id,),
        )
        self.db.commit()

    def _mark_failed(self, dispatch_id: int, current_attempts: int, error: str) -> None:
        next_attempts = current_attempts + 1
        backoff_seconds = self.BACKOFF_BASE * (2 ** current_attempts)
        self.db.execute(
            """
            UPDATE event_dispatches
            SET status = 'failed',
                attempts = %s,
                last_error = %s,
                next_retry = NOW() + make_interval(secs => %s)
            WHERE id = %s
            """,
            (next_attempts, error[:2000], backoff_seconds, dispatch_id),
        )
        self.db.commit()

    def _mark_exhausted(self, dispatch_id: int, reason: str) -> None:
        self.db.execute(
            """
            UPDATE event_dispatches
            SET status = 'exhausted', last_error = %s, completed_at = NOW()
            WHERE id = %s
            """,
            (reason, dispatch_id),
        )
        self.db.commit()
