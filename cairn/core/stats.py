"""Thread-safe model and pipeline stats. In-memory only — resets on restart."""

import threading
import time as _time
from collections import deque
from datetime import datetime, timezone


class ModelStats:
    """Track calls, tokens, errors, and derive health for a model backend."""

    def __init__(self, backend: str, model: str):
        self.backend = backend
        self.model = model
        self._lock = threading.RLock()
        self._calls = 0
        self._tokens_est = 0
        self._errors = 0
        self._last_call: datetime | None = None
        self._last_error: datetime | None = None
        self._last_error_msg: str | None = None
        # Rolling window of last 5 results: True = success, False = error
        self._recent: deque[bool] = deque(maxlen=5)

    def record_call(self, tokens_est: int = 0) -> None:
        with self._lock:
            self._calls += 1
            self._tokens_est += tokens_est
            self._last_call = datetime.now(timezone.utc)
            self._recent.append(True)

    def record_error(self, msg: str = "") -> None:
        with self._lock:
            self._errors += 1
            self._last_error = datetime.now(timezone.utc)
            self._last_error_msg = msg
            self._recent.append(False)

    @property
    def health(self) -> str:
        with self._lock:
            if not self._recent:
                return "unknown"
            recent = list(self._recent)
        # Last 3+ consecutive failures = unhealthy
        if len(recent) >= 3 and all(not r for r in recent[-3:]):
            return "unhealthy"
        # Any error in last 5 = degraded
        if any(not r for r in recent):
            return "degraded"
        return "healthy"

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "backend": self.backend,
                "model": self.model,
                "health": self.health,
                "stats": {
                    "calls": self._calls,
                    "tokens_est": self._tokens_est,
                    "errors": self._errors,
                    "last_call": self._last_call.isoformat() if self._last_call else None,
                    "last_error": self._last_error.isoformat() if self._last_error else None,
                    "last_error_msg": self._last_error_msg,
                },
            }


# Singletons — initialized by services.py on startup
embedding_stats: ModelStats | None = None
llm_stats: ModelStats | None = None


def init_embedding_stats(backend: str, model: str) -> ModelStats:
    global embedding_stats
    embedding_stats = ModelStats(backend, model)
    return embedding_stats


def init_llm_stats(backend: str, model: str) -> ModelStats:
    global llm_stats
    llm_stats = ModelStats(backend, model)
    return llm_stats


class EventBusStats:
    """Track event bus throughput, sessions, and SSE connections."""

    def __init__(self):
        self._lock = threading.RLock()
        self._events_published = 0
        self._events_by_type: dict[str, int] = {}
        self._sessions_opened = 0
        self._sessions_closed = 0
        self._sse_connections_active = 0
        self._sse_connections_total = 0
        self._sse_events_streamed = 0
        self._errors = 0
        self._last_event_at: datetime | None = None
        self._last_error: datetime | None = None
        self._last_error_msg: str | None = None
        self._started_at = datetime.now(timezone.utc)
        self._recent: deque[bool] = deque(maxlen=10)

    def record_publish(self, event_type: str) -> None:
        with self._lock:
            self._events_published += 1
            self._events_by_type[event_type] = self._events_by_type.get(event_type, 0) + 1
            self._last_event_at = datetime.now(timezone.utc)
            self._recent.append(True)

    def record_session_opened(self) -> None:
        with self._lock:
            self._sessions_opened += 1

    def record_session_closed(self) -> None:
        with self._lock:
            self._sessions_closed += 1

    def record_sse_connect(self) -> None:
        with self._lock:
            self._sse_connections_active += 1
            self._sse_connections_total += 1

    def record_sse_disconnect(self) -> None:
        with self._lock:
            self._sse_connections_active = max(0, self._sse_connections_active - 1)

    def record_sse_event(self) -> None:
        with self._lock:
            self._sse_events_streamed += 1

    def record_error(self, msg: str = "") -> None:
        with self._lock:
            self._errors += 1
            self._last_error = datetime.now(timezone.utc)
            self._last_error_msg = msg
            self._recent.append(False)

    @property
    def health(self) -> str:
        with self._lock:
            if not self._recent:
                return "unknown"
            recent = list(self._recent)
        if len(recent) >= 3 and all(not r for r in recent[-3:]):
            return "unhealthy"
        if any(not r for r in recent):
            return "degraded"
        return "healthy"

    def to_dict(self) -> dict:
        with self._lock:
            uptime_s = (_time.time() - self._started_at.timestamp())
            return {
                "health": self.health,
                "uptime_seconds": round(uptime_s),
                "events_published": self._events_published,
                "events_by_type": dict(self._events_by_type),
                "sessions_opened": self._sessions_opened,
                "sessions_closed": self._sessions_closed,
                "sse": {
                    "connections_active": self._sse_connections_active,
                    "connections_total": self._sse_connections_total,
                    "events_streamed": self._sse_events_streamed,
                },
                "errors": self._errors,
                "last_event_at": self._last_event_at.isoformat() if self._last_event_at else None,
                "last_error": self._last_error.isoformat() if self._last_error else None,
                "last_error_msg": self._last_error_msg,
            }


# Singletons — initialized by services.py on startup
event_bus_stats: EventBusStats | None = None


def init_event_bus_stats() -> EventBusStats:
    global event_bus_stats
    event_bus_stats = EventBusStats()
    return event_bus_stats


def emit_usage_event(
    operation: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: float = 0.0,
    success: bool = True,
    error_message: str | None = None,
) -> None:
    """Convenience function for embedding/LLM backends to emit usage events.

    Uses deferred import to avoid circular deps with analytics module.
    """
    from cairn.core.analytics import _analytics_tracker, UsageEvent

    if _analytics_tracker is None:
        return
    _analytics_tracker.track(UsageEvent(
        operation=operation,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        success=success,
        error_message=error_message[:512] if error_message else None,
    ))
