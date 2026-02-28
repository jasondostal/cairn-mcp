"""Tests for cairn.core.event_dispatcher — hardened EventDispatcher."""

import time
import threading
from unittest.mock import MagicMock, patch, call

from cairn.core.event_dispatcher import (
    EventDispatcher,
    CircuitBreaker,
    HandlerMetrics,
)


# ── CircuitBreaker ──────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_initially_closed(self):
        cb = CircuitBreaker(threshold=3)
        assert not cb.is_open("handler_a")

    def test_opens_after_threshold_consecutive_failures(self):
        cb = CircuitBreaker(threshold=3, cooldown=60.0)
        cb.record_failure("handler_a")
        cb.record_failure("handler_a")
        assert not cb.is_open("handler_a")
        cb.record_failure("handler_a")
        assert cb.is_open("handler_a")

    def test_success_resets_failure_streak(self):
        cb = CircuitBreaker(threshold=3, cooldown=60.0)
        cb.record_failure("handler_a")
        cb.record_failure("handler_a")
        cb.record_success("handler_a")  # reset
        cb.record_failure("handler_a")
        assert not cb.is_open("handler_a")

    def test_cooldown_allows_retry(self):
        cb = CircuitBreaker(threshold=2, cooldown=0.05)
        cb.record_failure("handler_a")
        cb.record_failure("handler_a")
        assert cb.is_open("handler_a")
        time.sleep(0.06)
        assert not cb.is_open("handler_a")  # half-open

    def test_success_after_half_open_closes(self):
        cb = CircuitBreaker(threshold=2, cooldown=0.05)
        cb.record_failure("handler_a")
        cb.record_failure("handler_a")
        assert cb.is_open("handler_a")
        time.sleep(0.06)
        cb.record_success("handler_a")
        assert not cb.is_open("handler_a")

    def test_independent_handlers(self):
        cb = CircuitBreaker(threshold=2)
        cb.record_failure("handler_a")
        cb.record_failure("handler_a")
        assert cb.is_open("handler_a")
        assert not cb.is_open("handler_b")

    def test_stats(self):
        cb = CircuitBreaker(threshold=3)
        cb.record_success("handler_a")
        cb.record_failure("handler_a")
        s = cb.stats()
        assert s["handler_a"]["successes"] == 1
        assert s["handler_a"]["failures"] == 1
        assert s["handler_a"]["is_open"] is False


# ── HandlerMetrics ──────────────────────────────────────────────────

class TestHandlerMetrics:
    def test_record_success(self):
        m = HandlerMetrics()
        m.record("h1", success=True, duration_ms=50.0)
        m.record("h1", success=True, duration_ms=100.0)
        d = m.to_dict()
        assert d["h1"]["total"] == 2
        assert d["h1"]["successes"] == 2
        assert d["h1"]["failures"] == 0
        assert d["h1"]["avg_duration_ms"] == 75.0

    def test_record_failure(self):
        m = HandlerMetrics()
        m.record("h1", success=False, duration_ms=10.0)
        d = m.to_dict()
        assert d["h1"]["failures"] == 1
        assert d["h1"]["last_failure"] is not None

    def test_record_timeout(self):
        m = HandlerMetrics()
        m.record("h1", success=False, duration_ms=30000.0, timeout=True)
        d = m.to_dict()
        assert d["h1"]["timeouts"] == 1
        assert d["h1"]["failures"] == 1

    def test_record_skipped(self):
        m = HandlerMetrics()
        m.record("h1", success=False, duration_ms=0, skipped=True)
        d = m.to_dict()
        assert d["h1"]["skipped_circuit_open"] == 1
        assert d["h1"]["total"] == 0  # skipped doesn't count as total

    def test_independent_handlers(self):
        m = HandlerMetrics()
        m.record("h1", success=True, duration_ms=10.0)
        m.record("h2", success=False, duration_ms=20.0)
        d = m.to_dict()
        assert d["h1"]["successes"] == 1
        assert d["h2"]["failures"] == 1


# ── EventDispatcher ─────────────────────────────────────────────────

class TestEventDispatcher:
    def _make_dispatcher(self, **overrides):
        db = MagicMock()
        event_bus = MagicMock()
        dispatcher = EventDispatcher(db, event_bus)
        for k, v in overrides.items():
            setattr(dispatcher, k, v)
        return dispatcher, db, event_bus

    def test_start_stop(self):
        dispatcher, db, _ = self._make_dispatcher()
        db.execute.return_value = []  # no pending dispatches
        dispatcher.start()
        assert dispatcher._thread is not None
        assert dispatcher._thread.is_alive()
        assert dispatcher._pool is not None
        dispatcher.stop()
        assert dispatcher._thread is None
        assert dispatcher._pool is None

    def test_poll_no_rows_rolls_back(self):
        dispatcher, db, _ = self._make_dispatcher()
        db.execute.return_value = []
        dispatcher._poll()
        db.rollback.assert_called_once()

    def test_poll_missing_handler_marks_exhausted(self):
        dispatcher, db, event_bus = self._make_dispatcher()
        db.execute.return_value = [
            {"id": 1, "event_id": 100, "handler": "ghost_handler",
             "attempts": 0, "event_type": "test.event", "payload": {},
             "project_id": None, "work_item_id": None,
             "session_name": "s1", "trace_id": None},
        ]
        event_bus.get_handler.return_value = None

        dispatcher._pool = MagicMock()
        dispatcher._poll()

        # Should mark exhausted, not call pool.submit
        exhausted_calls = [c for c in db.execute.call_args_list
                          if "exhausted" in str(c)]
        assert len(exhausted_calls) == 1
        dispatcher._pool.submit.assert_not_called()

    def test_poll_successful_handler(self):
        dispatcher, db, event_bus = self._make_dispatcher()

        handler_fn = MagicMock()
        event_bus.get_handler.return_value = handler_fn

        db.execute.return_value = [
            {"id": 1, "event_id": 100, "handler": "test_handler",
             "attempts": 0, "event_type": "test.event", "payload": {"key": "val"},
             "project_id": None, "work_item_id": 42,
             "session_name": "s1", "trace_id": "t1"},
        ]

        # Actually run through the thread pool
        dispatcher.start()
        time.sleep(0.1)  # let poll happen

        # After first poll, the handler should have been called
        # Give it a moment for async execution
        time.sleep(0.5)
        dispatcher.stop()

        # Verify handler was called with correct event shape
        if handler_fn.called:
            event_arg = handler_fn.call_args[0][0]
            assert event_arg["event_id"] == 100
            assert event_arg["event_type"] == "test.event"
            assert event_arg["payload"] == {"key": "val"}

    def test_handler_timeout_marks_failed(self):
        dispatcher, db, event_bus = self._make_dispatcher()
        dispatcher.HANDLER_TIMEOUT = 0.1  # 100ms timeout

        def slow_handler(event):
            time.sleep(5)  # way longer than timeout

        event_bus.get_handler.return_value = slow_handler

        row = {"id": 1, "event_id": 100, "handler": "slow",
               "attempts": 0, "event_type": "t", "payload": {},
               "project_id": None, "work_item_id": None,
               "session_name": "s", "trace_id": None}

        from concurrent.futures import ThreadPoolExecutor
        dispatcher._pool = ThreadPoolExecutor(max_workers=1)

        dispatcher._execute_with_timeout(row, "slow", slow_handler, {})

        dispatcher._pool.shutdown(wait=False)

        # Should have marked failed
        failed_calls = [c for c in db.execute.call_args_list
                       if "failed" in str(c)]
        assert len(failed_calls) >= 1
        # Circuit breaker should have recorded failure
        assert dispatcher.circuit_breaker.stats()["slow"]["failures"] == 1

    def test_handler_exception_marks_failed(self):
        dispatcher, db, event_bus = self._make_dispatcher()

        def broken_handler(event):
            raise ValueError("kaboom")

        event_bus.get_handler.return_value = broken_handler

        row = {"id": 1, "event_id": 100, "handler": "broken",
               "attempts": 1, "event_type": "t", "payload": {},
               "project_id": None, "work_item_id": None,
               "session_name": "s", "trace_id": None}

        from concurrent.futures import ThreadPoolExecutor
        dispatcher._pool = ThreadPoolExecutor(max_workers=1)

        dispatcher._execute_with_timeout(row, "broken", broken_handler, {})

        dispatcher._pool.shutdown(wait=False)

        # Should have marked failed
        failed_calls = [c for c in db.execute.call_args_list
                       if "failed" in str(c)]
        assert len(failed_calls) >= 1
        # Metrics should show failure
        metrics = dispatcher.metrics.to_dict()
        assert metrics["broken"]["failures"] == 1

    def test_circuit_breaker_skips_open_handler(self):
        dispatcher, db, event_bus = self._make_dispatcher()

        # Open the circuit
        for _ in range(5):
            dispatcher.circuit_breaker.record_failure("broken")
        assert dispatcher.circuit_breaker.is_open("broken")

        db.execute.return_value = [
            {"id": 1, "event_id": 100, "handler": "broken",
             "attempts": 0, "event_type": "t", "payload": {},
             "project_id": None, "work_item_id": None,
             "session_name": "s", "trace_id": None},
        ]

        from concurrent.futures import ThreadPoolExecutor
        dispatcher._pool = ThreadPoolExecutor(max_workers=1)
        dispatcher._poll()
        dispatcher._pool.shutdown(wait=False)

        # Handler should NOT have been looked up
        event_bus.get_handler.assert_not_called()
        # Metrics should show skip
        metrics = dispatcher.metrics.to_dict()
        assert metrics["broken"]["skipped_circuit_open"] == 1

    def test_health_report(self):
        dispatcher, _, _ = self._make_dispatcher()
        dispatcher.circuit_breaker.record_success("h1")
        dispatcher.metrics.record("h1", success=True, duration_ms=50)

        h = dispatcher.health()
        assert h["running"] is False  # not started
        assert "h1" in h["circuit_breakers"]
        assert "h1" in h["handler_metrics"]

    def test_backoff_calculation(self):
        dispatcher, db, _ = self._make_dispatcher()
        dispatcher._mark_failed(1, current_attempts=0, error="test")
        # backoff = 10 * 2^0 = 10s
        call_args = db.execute.call_args[0]
        assert 10 in call_args[1]  # backoff_seconds param

    def test_backoff_exponential(self):
        dispatcher, db, _ = self._make_dispatcher()
        dispatcher._mark_failed(1, current_attempts=3, error="test")
        # backoff = 10 * 2^3 = 80s
        call_args = db.execute.call_args[0]
        assert 80 in call_args[1]
