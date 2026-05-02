"""EventDispatcher — background worker that processes event dispatch records.

Polls the event_dispatches table for pending/failed records, resolves the
handler by name via EventBus, executes it, and tracks success/failure with
exponential backoff retry.

Hardened features (ca-108):
- Concurrent handler execution via ThreadPoolExecutor
- Per-handler timeout (configurable, default 30s)
- Circuit breaker — skip handlers failing repeatedly
- Per-handler metrics (execution time, success/failure counts)
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Per-handler circuit breaker.

    Tracks a rolling window of results. If the last N consecutive calls
    all fail, the breaker opens and the handler is skipped until the
    cooldown expires.
    """

    def __init__(self, threshold: int = 5, cooldown: float = 120.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self._lock = threading.Lock()
        # handler_name -> deque of bools (True=success, False=fail)
        self._results: dict[str, deque[bool]] = defaultdict(
            lambda: deque(maxlen=max(threshold, 10))
        )
        # handler_name -> timestamp when circuit opened
        self._open_since: dict[str, float] = {}

    def is_open(self, handler_name: str) -> bool:
        """Check if circuit is open (handler should be skipped)."""
        with self._lock:
            opened_at = self._open_since.get(handler_name)
            if opened_at is None:
                return False
            # Check cooldown
            if time.monotonic() - opened_at >= self.cooldown:
                # Half-open: allow one attempt
                del self._open_since[handler_name]
                return False
            return True

    def record_success(self, handler_name: str) -> None:
        with self._lock:
            self._results[handler_name].append(True)
            # Reset circuit on any success
            self._open_since.pop(handler_name, None)

    def record_failure(self, handler_name: str) -> None:
        with self._lock:
            results = self._results[handler_name]
            results.append(False)
            # Check if last N are all failures
            if len(results) >= self.threshold:
                tail = list(results)[-self.threshold:]
                if all(not r for r in tail):
                    self._open_since[handler_name] = time.monotonic()
                    logger.warning(
                        "CircuitBreaker: opened for handler '%s' after %d consecutive failures",
                        handler_name, self.threshold,
                    )

    def stats(self) -> dict[str, dict]:
        """Return per-handler circuit breaker state."""
        with self._lock:
            result = {}
            for name, results in self._results.items():
                recent = list(results)
                successes = sum(1 for r in recent if r)
                failures = sum(1 for r in recent if not r)
                result[name] = {
                    "successes": successes,
                    "failures": failures,
                    "is_open": name in self._open_since,
                }
            return result


class HandlerMetrics:
    """Thread-safe per-handler execution metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict[str, dict] = defaultdict(
            lambda: {
                "total": 0,
                "successes": 0,
                "failures": 0,
                "timeouts": 0,
                "skipped_circuit_open": 0,
                "total_duration_ms": 0.0,
                "last_success": None,
                "last_failure": None,
            }
        )

    def record(self, handler_name: str, success: bool, duration_ms: float,
               timeout: bool = False, skipped: bool = False) -> None:
        with self._lock:
            m = self._data[handler_name]
            if skipped:
                m["skipped_circuit_open"] += 1
                return
            m["total"] += 1
            m["total_duration_ms"] += duration_ms
            if timeout:
                m["timeouts"] += 1
                m["failures"] += 1
                m["last_failure"] = datetime.now(UTC).isoformat()
            elif success:
                m["successes"] += 1
                m["last_success"] = datetime.now(UTC).isoformat()
            else:
                m["failures"] += 1
                m["last_failure"] = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, dict]:
        with self._lock:
            result = {}
            for name, m in self._data.items():
                avg_ms = (m["total_duration_ms"] / m["total"]) if m["total"] else 0
                result[name] = {
                    **m,
                    "avg_duration_ms": round(avg_ms, 1),
                }
            return result


class EventDispatcher:
    """Background thread that reliably delivers events to registered handlers.

    Uses ThreadPoolExecutor for concurrent handler execution with per-handler
    timeouts and circuit breaker protection.
    """

    POLL_INTERVAL = 2.0     # seconds between polls
    BATCH_SIZE = 50         # max dispatches per poll cycle
    MAX_ATTEMPTS = 5        # give up after this many tries
    BACKOFF_BASE = 10       # seconds; actual = base * 2^attempts
    HANDLER_TIMEOUT = 30.0  # seconds; max time a single handler can run
    MAX_WORKERS = 4         # concurrent handler threads

    def __init__(self, db: Database, event_bus: EventBus):
        self.db = db
        self.event_bus = event_bus
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.circuit_breaker = CircuitBreaker()
        self.metrics = HandlerMetrics()
        self._pool: ThreadPoolExecutor | None = None

    def start(self) -> None:
        """Start the dispatch loop in a background thread."""
        self._stop_event.clear()
        self._pool = ThreadPoolExecutor(
            max_workers=self.MAX_WORKERS,
            thread_name_prefix="EventHandler",
        )
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="EventDispatcher",
        )
        self._thread.start()
        logger.info("EventDispatcher: started (workers=%d, timeout=%.0fs)", self.MAX_WORKERS, self.HANDLER_TIMEOUT)

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
        if self._pool:
            self._pool.shutdown(wait=False)
            self._pool = None

    def health(self) -> dict:
        """Return dispatcher health summary."""
        return {
            "running": self._thread is not None and self._thread.is_alive(),
            "circuit_breakers": self.circuit_breaker.stats(),
            "handler_metrics": self.metrics.to_dict(),
        }

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
        """Fetch pending dispatches and execute handlers concurrently."""
        rows = self.db.execute(
            """
            SELECT ed.id, ed.event_id, ed.handler, ed.attempts,
                   e.event_type, e.payload, e.project_id, e.work_item_id,
                   e.session_name, e.trace_id
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
            self.db.rollback()
            return

        processed = 0
        for row in rows:
            handler_name = row["handler"]

            # Circuit breaker check
            if self.circuit_breaker.is_open(handler_name):
                self.metrics.record(handler_name, success=False, duration_ms=0, skipped=True)
                logger.debug(
                    "EventDispatcher: skipping '%s' for event %d (circuit open)",
                    handler_name, row["event_id"],
                )
                # Don't increment attempts — just skip this cycle
                continue

            handler_fn = self.event_bus.get_handler(handler_name)
            if handler_fn is None:
                self._mark_exhausted(row["id"], f"handler '{handler_name}' not found")
                processed += 1
                continue

            event = {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "payload": row["payload"] or {},
                "project_id": row["project_id"],
                "work_item_id": row["work_item_id"],
                "session_name": row["session_name"],
                "trace_id": row["trace_id"],
            }

            self._execute_with_timeout(row, handler_name, handler_fn, event)
            processed += 1

        if processed:
            logger.info("EventDispatcher: processed %d dispatches", processed)

    def _execute_with_timeout(
        self, row: dict, handler_name: str, handler_fn, event: dict
    ) -> None:
        """Execute a handler with timeout enforcement via the thread pool."""
        if not self._pool:
            return

        t0 = time.monotonic()

        def _run_handler():
            try:
                return handler_fn(event)
            finally:
                self.db.release_if_held()

        future = self._pool.submit(_run_handler)

        try:
            future.result(timeout=self.HANDLER_TIMEOUT)
            duration_ms = (time.monotonic() - t0) * 1000
            self._mark_success(row["id"])
            self.circuit_breaker.record_success(handler_name)
            self.metrics.record(handler_name, success=True, duration_ms=duration_ms)
        except FutureTimeout:
            duration_ms = (time.monotonic() - t0) * 1000
            future.cancel()
            error_msg = f"handler '{handler_name}' timed out after {self.HANDLER_TIMEOUT}s"
            self._mark_failed(row["id"], row["attempts"], error_msg)
            self.circuit_breaker.record_failure(handler_name)
            self.metrics.record(handler_name, success=False, duration_ms=duration_ms, timeout=True)
            logger.warning(
                "EventDispatcher: %s for event %d (attempt %d)",
                error_msg, row["event_id"], row["attempts"] + 1,
            )
        except Exception:
            duration_ms = (time.monotonic() - t0) * 1000
            tb = traceback.format_exc()
            self._mark_failed(row["id"], row["attempts"], tb)
            self.circuit_breaker.record_failure(handler_name)
            self.metrics.record(handler_name, success=False, duration_ms=duration_ms)
            logger.warning(
                "EventDispatcher: handler '%s' failed for event %d (attempt %d)",
                handler_name, row["event_id"], row["attempts"] + 1,
            )

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
