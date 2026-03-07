"""Lightweight in-process rate limiter for expensive API endpoints.

Uses a sliding-window counter per client IP. No external dependencies.
For multi-worker deployments, replace with Redis-backed limiter.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class _SlidingWindow:
    """Per-key sliding window rate counter."""

    __slots__ = ("_requests", "_lock")

    def __init__(self):
        # key → list of timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if request is allowed and record it if so."""
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            timestamps = self._requests[key]
            # Prune expired entries
            timestamps[:] = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= max_requests:
                return False

            timestamps.append(now)
            return True

    def cleanup(self, max_age: int = 3600) -> None:
        """Remove keys with no recent activity."""
        now = time.monotonic()
        cutoff = now - max_age
        with self._lock:
            stale = [k for k, v in self._requests.items()
                     if not v or v[-1] < cutoff]
            for k in stale:
                del self._requests[k]


# Global rate limiter instance
_limiter = _SlidingWindow()

# Last cleanup timestamp
_last_cleanup = time.monotonic()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit expensive endpoints by client IP.

    Rules are (path_prefix, max_requests, window_seconds) tuples.
    """

    def __init__(self, app, rules: list[tuple[str, int, int]] | None = None):
        super().__init__(app)
        self.rules = rules or [
            # Chat/LLM — expensive (LLM API cost)
            ("/chat", 30, 60),
            # Ingest — expensive (embedding + enrichment)
            ("/ingest", 60, 60),
            # Search — moderate (embedding for semantic search)
            ("/search", 120, 60),
            # Auth — brute force prevention
            ("/auth/login", 10, 60),
            ("/auth/register", 5, 60),
        ]

    async def dispatch(self, request: Request, call_next):
        global _last_cleanup

        # Only rate-limit mutating/expensive operations
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path.rstrip("/")
        client_ip = request.client.host if request.client else "unknown"

        for prefix, max_req, window in self.rules:
            if path == prefix or path.startswith(prefix + "/"):
                key = f"{client_ip}:{prefix}"
                if not _limiter.is_allowed(key, max_req, window):
                    logger.warning(
                        "Rate limit exceeded: %s from %s (%d/%ds)",
                        prefix, client_ip, max_req, window,
                    )
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests. Please try again later."},
                        headers={"Retry-After": str(window)},
                    )
                break

        # Periodic cleanup (every 10 minutes)
        now = time.monotonic()
        if now - _last_cleanup > 600:
            _last_cleanup = now
            _limiter.cleanup()

        return await call_next(request)
