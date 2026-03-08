"""Thread-pool helper for MCP tool handlers (ca-237).

Runs synchronous service calls in a thread and releases the DB connection
afterward to prevent pool exhaustion.
"""

import asyncio
import logging

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
    """

    def _wrapped():
        try:
            return fn(*args, **kwargs)
        finally:
            if _db is not None:
                _db._release()

    try:
        return await asyncio.wait_for(asyncio.to_thread(_wrapped), timeout=timeout)
    except TimeoutError:
        logger.error("Tool operation timed out after %.0fs", timeout)
        raise
