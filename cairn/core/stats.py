"""Thread-safe model invocation stats. In-memory only — resets on restart."""

import threading
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
