"""Thread-pool helper for MCP tool handlers (ca-237).

Runs synchronous service calls in a thread and releases the DB connection
afterward to prevent pool exhaustion.

Also the universal instrumentation point — every MCP tool call passes
through ``in_thread``, so we emit a ``tool.*`` event into the unified event
bus. Tool name and project are read from the trace context (set by each
tool handler before calling ``in_thread``).
"""

import asyncio
import logging
import time

from cairn.core import stats
from cairn.core.trace import current_trace
from cairn.storage.database import Database

logger = logging.getLogger("cairn")


async def in_thread(_db: Database, fn, *args, timeout: float = 120.0, **kwargs):
    """Run *fn* in a thread, then release the DB connection back to the pool.

    The Database class uses ``threading.local()`` to hold connections per-thread.
    With ``asyncio.to_thread()``, worker threads from the ThreadPoolExecutor
    check out connections but never return them — causing pool exhaustion
    and deadlock after enough concurrent calls.  This wrapper ensures every
    thread returns its connection when the work is done.

    A *timeout* (default 120 s) prevents hung operations from blocking forever.
    The DB connection is released even on timeout (via the finally block in
    ``_wrapped`` — the thread still runs to completion and hits finally).

    Automatically emits a ``tool.*`` event into the unified event bus using
    tool_name and project from the trace context.
    """
    # Capture trace context before the thread hop (contextvars don't propagate)
    trace = current_trace()
    _tool_name = trace.tool_name if trace else None
    _project = trace.project if trace else None

    def _wrapped():
        try:
            return fn(*args, **kwargs)
        finally:
            if _db is not None:
                _db._release()

    t0 = time.monotonic()
    success = True
    try:
        result = await asyncio.wait_for(asyncio.to_thread(_wrapped), timeout=timeout)
        return result
    except TimeoutError:
        success = False
        logger.error("Tool operation timed out after %.0fs", timeout)
        raise
    except Exception:
        success = False
        raise
    finally:
        latency_ms = (time.monotonic() - t0) * 1000
        event_bus = stats.get_event_bus()
        logger.info(
            "in_thread exit: tool=%s project=%s latency=%.0fms success=%s bus=%s",
            _tool_name, _project, latency_ms, success, event_bus is not None,
        )
        if event_bus and _tool_name:
            event_bus.emit(
                f"tool.{_tool_name}",
                tool_name=_tool_name,
                project=_project,
                payload={"latency_ms": latency_ms, "success": success},
            )
