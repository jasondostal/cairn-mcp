"""Tests for cairn.tools.threading.in_thread helper.

Verifies that:
- Normal execution runs fn and releases DB connection
- Exceptions in fn still trigger db._release()
- Timeout raises asyncio.TimeoutError
"""

import asyncio
import time
from unittest.mock import MagicMock, call

import pytest

from cairn.tools.threading import in_thread


# ---------------------------------------------------------------------------
# Normal execution
# ---------------------------------------------------------------------------

class TestInThreadNormal:
    def test_fn_result_returned(self):
        db = MagicMock()

        async def _run():
            return await in_thread(db, lambda: 42)

        result = asyncio.run(_run())
        assert result == 42

    def test_db_release_called(self):
        db = MagicMock()

        async def _run():
            return await in_thread(db, lambda: "ok")

        asyncio.run(_run())
        db._release.assert_called_once()

    def test_fn_receives_args(self):
        db = MagicMock()
        calls = []

        def fn(a, b, c=None):
            calls.append((a, b, c))
            return "done"

        async def _run():
            return await in_thread(db, fn, 1, 2, c=3)

        result = asyncio.run(_run())
        assert result == "done"
        assert calls == [(1, 2, 3)]
        db._release.assert_called_once()

    def test_db_none_is_safe(self):
        """When db is None, _release should not be called (no AttributeError)."""
        async def _run():
            return await in_thread(None, lambda: "ok")

        result = asyncio.run(_run())
        assert result == "ok"


# ---------------------------------------------------------------------------
# Exception in fn
# ---------------------------------------------------------------------------

class TestInThreadException:
    def test_exception_propagates(self):
        db = MagicMock()

        def boom():
            raise ValueError("bad input")

        async def _run():
            return await in_thread(db, boom)

        with pytest.raises(ValueError, match="bad input"):
            asyncio.run(_run())

    def test_db_release_called_on_exception(self):
        db = MagicMock()

        def boom():
            raise RuntimeError("crash")

        async def _run():
            return await in_thread(db, boom)

        with pytest.raises(RuntimeError):
            asyncio.run(_run())

        # _release must still be called (finally block)
        db._release.assert_called_once()


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestInThreadTimeout:
    def test_timeout_raises_timeout_error(self):
        db = MagicMock()

        def slow_fn():
            time.sleep(5)
            return "too slow"

        async def _run():
            return await in_thread(db, slow_fn, timeout=0.1)

        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(_run())

    def test_custom_timeout_value(self):
        """Verify that a very short timeout triggers quickly."""
        db = MagicMock()

        def slow_fn():
            time.sleep(10)
            return "never"

        async def _run():
            start = time.monotonic()
            try:
                await in_thread(db, slow_fn, timeout=0.05)
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - start
                return elapsed

        elapsed = asyncio.run(_run())
        # Should timeout in well under 1 second
        assert elapsed < 1.0


# ---------------------------------------------------------------------------
# Thread safety: release happens in the worker thread
# ---------------------------------------------------------------------------

class TestInThreadRelease:
    def test_release_called_in_worker_thread(self):
        """Verify _release is called from within the thread (not the event loop thread)."""
        import threading
        db = MagicMock()
        release_thread_id = []

        original_release = db._release

        def tracking_release():
            release_thread_id.append(threading.current_thread().ident)

        db._release = tracking_release
        main_thread = threading.current_thread().ident

        async def _run():
            return await in_thread(db, lambda: "ok")

        asyncio.run(_run())

        assert len(release_thread_id) == 1
        # The release should happen in a different thread than the main one
        assert release_thread_id[0] != main_thread
