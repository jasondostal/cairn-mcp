"""Tests for cairn.core.analytics — UsageEvent, UsageTracker, track_operation, RollupWorker, query engine."""

import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from cairn.core.analytics import (
    AnalyticsQueryEngine,
    UsageEvent,
    UsageTracker,
    RollupWorker,
    track_operation,
    init_analytics_tracker,
)
from cairn.core.stats import emit_usage_event
import cairn.core.analytics as analytics_mod
import cairn.core.stats as stats_mod


class TestUsageEvent:
    def test_defaults(self):
        ev = UsageEvent(operation="store")
        assert ev.operation == "store"
        assert ev.success is True
        assert ev.tokens_in == 0
        assert ev.tokens_out == 0
        assert ev.latency_ms == 0.0
        assert ev.project_id is None
        assert ev.error_message is None

    def test_custom_values(self):
        ev = UsageEvent(
            operation="search",
            project_id=5,
            tokens_in=100,
            tokens_out=200,
            latency_ms=42.5,
            success=False,
            error_message="timeout",
        )
        assert ev.operation == "search"
        assert ev.project_id == 5
        assert ev.tokens_in == 100
        assert ev.success is False
        assert ev.error_message == "timeout"


class TestUsageTracker:
    def test_track_enqueues(self):
        db = MagicMock()
        tracker = UsageTracker(db)
        ev = UsageEvent(operation="store")
        tracker.track(ev)
        assert tracker._queue.qsize() == 1

    def test_track_drops_when_full(self):
        db = MagicMock()
        tracker = UsageTracker(db)
        tracker.QUEUE_MAX = 2
        tracker._queue = __import__("queue").Queue(maxsize=2)
        tracker.track(UsageEvent(operation="a"))
        tracker.track(UsageEvent(operation="b"))
        tracker.track(UsageEvent(operation="c"))  # should drop silently
        assert tracker._queue.qsize() == 2

    def test_flush_batch_inserts(self):
        db = MagicMock()
        db.execute = MagicMock()
        db.commit = MagicMock()
        tracker = UsageTracker(db)
        tracker.track(UsageEvent(operation="store"))
        tracker.track(UsageEvent(operation="search"))
        tracker._flush_batch()
        assert db.execute.call_count == 2
        db.commit.assert_called_once()

    def test_flush_batch_empty_noop(self):
        db = MagicMock()
        tracker = UsageTracker(db)
        tracker._flush_batch()
        db.execute.assert_not_called()
        db.commit.assert_not_called()


class TestTrackOperation:
    def test_successful_call(self):
        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value={"id": 1})

        @track_operation("test_op", tracker=tracker)
        def my_func(project=None):
            return {"result": "ok"}

        result = my_func(project="myproject")
        assert result == {"result": "ok"}
        tracker.track.assert_called_once()
        event = tracker.track.call_args[0][0]
        assert event.operation == "test_op"
        assert event.success is True
        assert event.latency_ms > 0

    def test_error_dict_return(self):
        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value=None)

        @track_operation("test_op", tracker=tracker)
        def my_func():
            return {"error": "something went wrong"}

        result = my_func()
        assert result == {"error": "something went wrong"}
        event = tracker.track.call_args[0][0]
        assert event.success is False
        assert event.error_message == "something went wrong"

    def test_exception_propagates(self):
        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value=None)

        @track_operation("test_op", tracker=tracker)
        def my_func():
            raise ValueError("boom")

        try:
            my_func()
            assert False, "Should have raised"
        except ValueError:
            pass

        event = tracker.track.call_args[0][0]
        assert event.success is False
        assert "boom" in event.error_message

    def test_no_tracker_passthrough(self):
        @track_operation("test_op", tracker=None)
        def my_func():
            return {"ok": True}

        assert my_func() == {"ok": True}

    def test_module_singleton(self):
        """When no tracker= is passed, uses the module-level singleton."""
        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value=None)

        old = analytics_mod._analytics_tracker
        try:
            init_analytics_tracker(tracker)

            @track_operation("singleton_op")
            def my_func():
                return {"ok": True}

            result = my_func()
            assert result == {"ok": True}
            tracker.track.assert_called_once()
            event = tracker.track.call_args[0][0]
            assert event.operation == "singleton_op"
        finally:
            analytics_mod._analytics_tracker = old

    def test_positional_project_extraction(self):
        """Extracts project from positional args (like core method calls)."""
        tracker = MagicMock()
        tracker.db = MagicMock()
        tracker.db.execute_one = MagicMock(return_value={"id": 42})

        @track_operation("test_op", tracker=tracker)
        def my_func(self, content, project, session_name=None):
            return {"ok": True}

        my_func(None, "hello", "myproject", session_name="sess-1")
        event = tracker.track.call_args[0][0]
        assert event.project_id == 42
        assert event.session_name == "sess-1"


class TestRollupWorkerPercentile:
    def test_percentile_single(self):
        assert RollupWorker._percentile([10.0], 50) == 10.0

    def test_percentile_multiple(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        p50 = RollupWorker._percentile(vals, 50)
        assert p50 == 3.0

    def test_percentile_p95(self):
        vals = list(range(1, 101))
        p95 = RollupWorker._percentile([float(v) for v in vals], 95)
        assert p95 is not None
        assert 94 <= p95 <= 96

    def test_percentile_empty(self):
        assert RollupWorker._percentile([], 50) is None


class TestEmitUsageEvent:
    def test_emit_with_tracker(self):
        """emit_usage_event enqueues when tracker is set."""
        tracker = MagicMock()
        old = analytics_mod._analytics_tracker
        try:
            analytics_mod._analytics_tracker = tracker
            emit_usage_event("embed", "titan-v2", tokens_in=100, latency_ms=50.0)
            tracker.track.assert_called_once()
            event = tracker.track.call_args[0][0]
            assert event.operation == "embed"
            assert event.model == "titan-v2"
            assert event.tokens_in == 100
            assert event.latency_ms == 50.0
            assert event.success is True
        finally:
            analytics_mod._analytics_tracker = old

    def test_emit_without_tracker(self):
        """emit_usage_event is a no-op when tracker is None."""
        old = analytics_mod._analytics_tracker
        try:
            analytics_mod._analytics_tracker = None
            # Should not raise
            emit_usage_event("embed", "titan-v2", tokens_in=100)
        finally:
            analytics_mod._analytics_tracker = old

    def test_emit_error_truncates(self):
        """Error messages are truncated to 512 chars."""
        tracker = MagicMock()
        old = analytics_mod._analytics_tracker
        try:
            analytics_mod._analytics_tracker = tracker
            long_msg = "x" * 1000
            emit_usage_event("llm.generate", "model", success=False, error_message=long_msg)
            event = tracker.track.call_args[0][0]
            assert len(event.error_message) == 512
        finally:
            analytics_mod._analytics_tracker = old


class TestMemoryTypeGrowth:
    def test_returns_series_and_types(self):
        """memory_type_growth returns proper structure."""
        now = datetime.now(timezone.utc)
        db = MagicMock()
        db.execute = MagicMock(return_value=[
            {"bucket": now - timedelta(days=2), "memory_type": "note", "cnt": 5},
            {"bucket": now - timedelta(days=2), "memory_type": "decision", "cnt": 3},
            {"bucket": now - timedelta(days=1), "memory_type": "note", "cnt": 2},
        ])
        engine = AnalyticsQueryEngine(db)
        result = engine.memory_type_growth(days=7, granularity="day")

        assert "series" in result
        assert "types" in result
        assert "decision" in result["types"]
        assert "note" in result["types"]
        assert len(result["series"]) == 2  # 2 distinct buckets
        # Cumulative: last point should have note=7 (5+2), decision=3
        last = result["series"][-1]
        assert last["note"] == 7
        assert last["decision"] == 3

    def test_empty(self):
        db = MagicMock()
        db.execute = MagicMock(return_value=[])
        engine = AnalyticsQueryEngine(db)
        result = engine.memory_type_growth(days=7)
        assert result["series"] == []
        assert result["types"] == []


class TestEntityCountsSparkline:
    def test_returns_totals_and_sparklines(self):
        db = MagicMock()
        db.execute_one = MagicMock(return_value={
            "memories": 100, "projects": 5, "cairns": 20, "clusters": 3,
        })
        now = datetime.now(timezone.utc)
        db.execute = MagicMock(return_value=[
            {"bucket": now - timedelta(days=1), "cnt": 10},
            {"bucket": now, "cnt": 5},
        ])
        engine = AnalyticsQueryEngine(db)
        result = engine.entity_counts_sparkline(days=30)

        assert result["totals"]["memories"] == 100
        assert result["totals"]["projects"] == 5
        assert "sparklines" in result
        assert "memories" in result["sparklines"]
        # 4 entity types queried (memories, projects, cairns, clusters)
        assert db.execute.call_count == 4


class TestActivityHeatmap:
    def test_returns_day_list(self):
        db = MagicMock()
        now = datetime.now(timezone.utc)
        db.execute = MagicMock(return_value=[
            {"bucket": now - timedelta(days=1), "cnt": 42},
            {"bucket": now, "cnt": 15},
        ])
        engine = AnalyticsQueryEngine(db)
        result = engine.activity_heatmap(days=365)

        assert "days" in result
        assert len(result["days"]) == 2
        assert result["days"][0]["count"] == 42
        assert result["days"][1]["count"] == 15

    def test_empty(self):
        db = MagicMock()
        db.execute = MagicMock(return_value=[])
        engine = AnalyticsQueryEngine(db)
        result = engine.activity_heatmap(days=365)
        assert result["days"] == []
