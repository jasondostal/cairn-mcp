"""MetricsCollector — in-memory sliding window aggregator.

Subscribes to the event bus and accumulates counters into time-based buckets.
Provides a real-time metrics stream for SSE consumers (dashboards, extensions).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

RING_BUFFER_SIZE = 60  # keep last 60 buckets of history
BUCKET_INTERVAL_S = 5  # seconds per bucket (5s × 60 = 5 min window)


@dataclass
class MetricsBucket:
    """One-second aggregation bucket."""

    timestamp: str  # ISO format
    ops_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    errors: int = 0
    active_sessions: int = 0
    by_tool: dict[str, int] = field(default_factory=dict)
    by_project: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)
    by_event_type: dict[str, int] = field(default_factory=dict)
    latency_avg_ms: float = 0.0

    # Internal tracking (not serialized)
    _latency_sum: float = field(default=0.0, repr=False)
    _latency_count: int = field(default=0, repr=False)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "ops_count": self.ops_count,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "errors": self.errors,
            "active_sessions": self.active_sessions,
            "by_tool": self.by_tool,
            "by_project": self.by_project,
            "by_category": self.by_category,
            "by_event_type": self.by_event_type,
            "latency_avg_ms": round(self.latency_avg_ms, 2),
        }


# ---------------------------------------------------------------------------
# Event-type → category mapping
# ---------------------------------------------------------------------------

_CATEGORY_MAP: dict[str, str] = {
    # Reads
    "search.executed": "reads",
    "memory.recalled": "reads",
    # Writes
    "memory.created": "writes",
    "memory.modified": "writes",
    "memory.deleted": "writes",
    "memory.consolidated": "writes",
    "working_memory.captured": "writes",
    "belief.crystallized": "writes",
    "belief.updated": "writes",
    # Work items
    "work_item.created": "work",
    "work_item.updated": "work",
    "work_item.completed": "work",
    "work_item.blocked": "work",
    "work_item.unblocked": "work",
    # Sessions
    "session_start": "sessions",
    "session_end": "sessions",
    # System / background
    "settings.updated": "system",
    "working_memory.archived": "system",
    "working_memory.resolved": "system",
    # Tool-layer events (from in_thread instrumentation)
    "tool.search": "reads",
    "tool.recall": "reads",
    "tool.code_query": "reads",
    "tool.orient": "reads",
    "tool.rules": "reads",
    "tool.status": "reads",
    "tool.insights": "reads",
    "tool.drift_check": "reads",
    "tool.decay_scan": "reads",
    "tool.store": "writes",
    "tool.modify": "writes",
    "tool.ingest": "writes",
    "tool.consolidate": "writes",
    "tool.work_items": "work",
    "tool.deliverables": "work",
    "tool.dispatch": "work",
    "tool.locks": "work",
    "tool.suggest_agent": "work",
    "tool.projects": "reads",
    "tool.think": "llm",
    "tool.beliefs": "reads",
    "tool.arch_check": "llm",
    "tool.working_memory": "reads",
}

# Prefix fallbacks for event types not in the explicit map
_CATEGORY_PREFIX_MAP: dict[str, str] = {
    "memory.": "writes",
    "search.": "reads",
    "work_item.": "work",
    "belief.": "writes",
    "working_memory.": "system",
    "session": "sessions",
    "tool.": "other",
}


def categorize_event(event_type: str) -> str:
    """Map an event_type to a high-level category."""
    cat = _CATEGORY_MAP.get(event_type)
    if cat:
        return cat
    for prefix, fallback in _CATEGORY_PREFIX_MAP.items():
        if event_type.startswith(prefix):
            return fallback
    return "other"


class MetricsCollector:
    """In-memory 1-second sliding window metrics aggregator.

    Lifecycle: start() begins the background tick thread, stop() halts it.
    Thread-safe — all counter mutations are protected by a lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: MetricsBucket = self._new_bucket()
        self._ring: deque[MetricsBucket] = deque(maxlen=RING_BUFFER_SIZE)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Async subscribers (SSE endpoints)
        self._subscribers: list[asyncio.Queue[MetricsBucket]] = []
        self._sub_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Recording events
    # ------------------------------------------------------------------

    def record_event(
        self,
        *,
        event_type: str = "",
        tool_name: str | None = None,
        project: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: float = 0.0,
        success: bool = True,
        session_name: str | None = None,
        category: str | None = None,
    ) -> None:
        """Record a single event into the current bucket. Thread-safe."""
        with self._lock:
            self._current.ops_count += 1
            logger.info(
                "MetricsCollector.record_event: type=%s tool=%s ops_count=%d",
                event_type, tool_name, self._current.ops_count,
            )
            self._current.tokens_in += tokens_in
            self._current.tokens_out += tokens_out
            if not success:
                self._current.errors += 1
            if tool_name:
                self._current.by_tool[tool_name] = self._current.by_tool.get(tool_name, 0) + 1
            if project:
                self._current.by_project[project] = self._current.by_project.get(project, 0) + 1
            # Category tracking
            cat = category or (categorize_event(event_type) if event_type else "other")
            self._current.by_category[cat] = self._current.by_category.get(cat, 0) + 1
            if event_type:
                self._current.by_event_type[event_type] = (
                    self._current.by_event_type.get(event_type, 0) + 1
                )
            if latency_ms > 0:
                self._current._latency_sum += latency_ms
                self._current._latency_count += 1
                self._current.latency_avg_ms = (
                    self._current._latency_sum / self._current._latency_count
                )

    def set_active_sessions(self, count: int) -> None:
        """Update the active session count (called periodically or on change)."""
        with self._lock:
            self._current.active_sessions = count

    # ------------------------------------------------------------------
    # Event bus handler (wired via subscribe)
    # ------------------------------------------------------------------

    def handle_event(self, event_data: dict) -> None:
        """EventBus handler — extract metrics from published events."""
        payload = event_data.get("payload") or {}
        self.record_event(
            event_type=event_data.get("event_type", ""),
            tool_name=event_data.get("tool_name"),
            project=event_data.get("project"),
            tokens_in=payload.get("tokens_in", 0),
            tokens_out=payload.get("tokens_out", 0),
            latency_ms=payload.get("latency_ms", 0.0),
            success=payload.get("success", True),
            session_name=event_data.get("session_name"),
        )

    # ------------------------------------------------------------------
    # Read interface
    # ------------------------------------------------------------------

    def snapshot(self) -> MetricsBucket:
        """Return a copy of the current bucket."""
        with self._lock:
            return MetricsBucket(
                timestamp=self._current.timestamp,
                ops_count=self._current.ops_count,
                tokens_in=self._current.tokens_in,
                tokens_out=self._current.tokens_out,
                errors=self._current.errors,
                active_sessions=self._current.active_sessions,
                by_tool=dict(self._current.by_tool),
                by_project=dict(self._current.by_project),
                by_category=dict(self._current.by_category),
                by_event_type=dict(self._current.by_event_type),
                latency_avg_ms=self._current.latency_avg_ms,
            )

    def history(self) -> list[MetricsBucket]:
        """Return the ring buffer contents (oldest first)."""
        with self._lock:
            return list(self._ring)

    async def subscribe(self) -> asyncio.Queue[MetricsBucket]:
        """Return a queue that receives a MetricsBucket every tick."""
        q: asyncio.Queue[MetricsBucket] = asyncio.Queue(maxsize=120)
        with self._sub_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[MetricsBucket]) -> None:
        """Remove a subscriber queue."""
        with self._sub_lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background tick thread."""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._tick_loop, daemon=True, name="MetricsCollector",
        )
        self._thread.start()
        logger.info("MetricsCollector: started")

    def stop(self) -> None:
        """Stop the tick thread."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            logger.warning("MetricsCollector: thread did not stop within timeout")
        else:
            logger.info("MetricsCollector: stopped")
        self._thread = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _new_bucket() -> MetricsBucket:
        return MetricsBucket(timestamp=datetime.now(UTC).isoformat())

    def _tick_loop(self) -> None:
        """Roll the bucket every BUCKET_INTERVAL_S and notify subscribers."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=BUCKET_INTERVAL_S)
            if self._stop_event.is_set():
                break
            self._roll_bucket()

    def _roll_bucket(self) -> None:
        """Finalize the current bucket, push to ring buffer, notify subscribers."""
        with self._lock:
            finished = self._current
            self._current = self._new_bucket()
            # Carry forward active_sessions (it's a gauge, not a counter)
            self._current.active_sessions = finished.active_sessions
            self._ring.append(finished)

        # Notify async subscribers (non-blocking)
        with self._sub_lock:
            dead: list[asyncio.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(finished)
                except asyncio.QueueFull:
                    dead.append(q)
            # Clean up dead subscribers
            for q in dead:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass
