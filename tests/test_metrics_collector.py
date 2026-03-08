"""Tests for cairn.core.metrics_collector — MetricsCollector and MetricsBucket."""

import asyncio
import threading
import time

from cairn.core.metrics_collector import MetricsBucket, MetricsCollector, RING_BUFFER_SIZE


class TestMetricsBucket:
    def test_defaults(self):
        b = MetricsBucket(timestamp="2026-01-01T00:00:00")
        assert b.ops_count == 0
        assert b.tokens_in == 0
        assert b.tokens_out == 0
        assert b.errors == 0
        assert b.active_sessions == 0
        assert b.by_tool == {}
        assert b.by_project == {}
        assert b.latency_avg_ms == 0.0

    def test_to_dict(self):
        b = MetricsBucket(
            timestamp="2026-01-01T00:00:00",
            ops_count=5,
            tokens_in=100,
            tokens_out=200,
            errors=1,
            active_sessions=2,
            by_tool={"store": 3, "search": 2},
            by_project={"proj1": 5},
            latency_avg_ms=42.567,
        )
        d = b.to_dict()
        assert d["timestamp"] == "2026-01-01T00:00:00"
        assert d["ops_count"] == 5
        assert d["tokens_in"] == 100
        assert d["tokens_out"] == 200
        assert d["errors"] == 1
        assert d["active_sessions"] == 2
        assert d["by_tool"] == {"store": 3, "search": 2}
        assert d["by_project"] == {"proj1": 5}
        assert d["latency_avg_ms"] == 42.57  # rounded to 2 decimal places

    def test_to_dict_excludes_internal_fields(self):
        b = MetricsBucket(timestamp="2026-01-01T00:00:00")
        d = b.to_dict()
        assert "_latency_sum" not in d
        assert "_latency_count" not in d


class TestMetricsCollectorRecording:
    def test_record_event_increments_counters(self):
        mc = MetricsCollector()
        mc.record_event(event_type="test", tokens_in=10, tokens_out=20)
        snap = mc.snapshot()
        assert snap.ops_count == 1
        assert snap.tokens_in == 10
        assert snap.tokens_out == 20

    def test_record_event_tracks_errors(self):
        mc = MetricsCollector()
        mc.record_event(success=False)
        mc.record_event(success=True)
        mc.record_event(success=False)
        snap = mc.snapshot()
        assert snap.ops_count == 3
        assert snap.errors == 2

    def test_record_event_tracks_by_tool(self):
        mc = MetricsCollector()
        mc.record_event(tool_name="store")
        mc.record_event(tool_name="store")
        mc.record_event(tool_name="search")
        snap = mc.snapshot()
        assert snap.by_tool == {"store": 2, "search": 1}

    def test_record_event_tracks_by_project(self):
        mc = MetricsCollector()
        mc.record_event(project="alpha")
        mc.record_event(project="alpha")
        mc.record_event(project="beta")
        snap = mc.snapshot()
        assert snap.by_project == {"alpha": 2, "beta": 1}

    def test_record_event_computes_latency_avg(self):
        mc = MetricsCollector()
        mc.record_event(latency_ms=10.0)
        mc.record_event(latency_ms=30.0)
        snap = mc.snapshot()
        assert snap.latency_avg_ms == 20.0

    def test_record_event_ignores_zero_latency(self):
        mc = MetricsCollector()
        mc.record_event(latency_ms=0.0)
        mc.record_event(latency_ms=10.0)
        snap = mc.snapshot()
        # Only the non-zero latency should count
        assert snap.latency_avg_ms == 10.0

    def test_set_active_sessions(self):
        mc = MetricsCollector()
        mc.set_active_sessions(5)
        snap = mc.snapshot()
        assert snap.active_sessions == 5


class TestMetricsCollectorSnapshot:
    def test_snapshot_returns_copy(self):
        mc = MetricsCollector()
        mc.record_event(tokens_in=10)
        snap1 = mc.snapshot()
        mc.record_event(tokens_in=20)
        snap2 = mc.snapshot()
        # snap1 should not be affected by the second record
        assert snap1.tokens_in == 10
        assert snap2.tokens_in == 30


class TestMetricsCollectorHandleEvent:
    def test_handle_event_extracts_fields(self):
        mc = MetricsCollector()
        mc.handle_event({
            "event_type": "memory.stored",
            "tool_name": "store",
            "project": "cairn",
            "session_name": "sess-1",
            "payload": {
                "tokens_in": 50,
                "tokens_out": 100,
                "latency_ms": 25.0,
                "success": True,
            },
        })
        snap = mc.snapshot()
        assert snap.ops_count == 1
        assert snap.tokens_in == 50
        assert snap.tokens_out == 100
        assert snap.by_tool == {"store": 1}
        assert snap.by_project == {"cairn": 1}
        assert snap.latency_avg_ms == 25.0

    def test_handle_event_handles_missing_payload(self):
        mc = MetricsCollector()
        mc.handle_event({"event_type": "test"})
        snap = mc.snapshot()
        assert snap.ops_count == 1
        assert snap.tokens_in == 0


class TestMetricsCollectorBucketRoll:
    def test_roll_bucket_moves_to_ring(self):
        mc = MetricsCollector()
        mc.record_event(tokens_in=10)
        mc._roll_bucket()
        # Current bucket should be fresh
        snap = mc.snapshot()
        assert snap.ops_count == 0
        assert snap.tokens_in == 0
        # History should have the old bucket
        history = mc.history()
        assert len(history) == 1
        assert history[0].tokens_in == 10

    def test_roll_bucket_carries_forward_active_sessions(self):
        mc = MetricsCollector()
        mc.set_active_sessions(3)
        mc._roll_bucket()
        snap = mc.snapshot()
        assert snap.active_sessions == 3

    def test_ring_buffer_limited_to_60(self):
        mc = MetricsCollector()
        for i in range(70):
            mc.record_event(tokens_in=i)
            mc._roll_bucket()
        history = mc.history()
        assert len(history) == RING_BUFFER_SIZE  # 60
        # Oldest should be bucket #10 (0-9 evicted)
        assert history[0].tokens_in == 10


class TestMetricsCollectorSubscribe:
    def test_subscribe_yields_buckets(self):
        mc = MetricsCollector()

        async def _test():
            q = await mc.subscribe()
            mc.record_event(tokens_in=42)
            mc._roll_bucket()
            bucket = await asyncio.wait_for(q.get(), timeout=2.0)
            assert bucket.tokens_in == 42
            mc.unsubscribe(q)

        asyncio.run(_test())

    def test_unsubscribe_removes_queue(self):
        mc = MetricsCollector()

        async def _test():
            q = await mc.subscribe()
            assert len(mc._subscribers) == 1
            mc.unsubscribe(q)
            assert len(mc._subscribers) == 0

        asyncio.run(_test())

    def test_unsubscribe_idempotent(self):
        mc = MetricsCollector()

        async def _test():
            q = await mc.subscribe()
            mc.unsubscribe(q)
            mc.unsubscribe(q)  # should not raise
            assert len(mc._subscribers) == 0

        asyncio.run(_test())


class TestMetricsCollectorThreadSafety:
    def test_concurrent_record_calls(self):
        mc = MetricsCollector()
        n_threads = 10
        n_per_thread = 100
        barrier = threading.Barrier(n_threads)

        def _worker():
            barrier.wait()
            for _ in range(n_per_thread):
                mc.record_event(tokens_in=1, tokens_out=1)

        threads = [threading.Thread(target=_worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snap = mc.snapshot()
        assert snap.ops_count == n_threads * n_per_thread
        assert snap.tokens_in == n_threads * n_per_thread
        assert snap.tokens_out == n_threads * n_per_thread


class TestMetricsCollectorLifecycle:
    def test_start_stop(self):
        mc = MetricsCollector()
        mc.start()
        assert mc._thread is not None
        assert mc._thread.is_alive()
        mc.stop()
        assert mc._thread is None

    def test_start_idempotent(self):
        mc = MetricsCollector()
        mc.start()
        t1 = mc._thread
        mc.start()  # should not create a second thread
        assert mc._thread is t1
        mc.stop()

    def test_stop_without_start(self):
        mc = MetricsCollector()
        mc.stop()  # should not raise

    def test_tick_rolls_bucket(self):
        mc = MetricsCollector()
        mc.record_event(tokens_in=7)
        mc.start()
        # Wait for at least one tick
        time.sleep(1.5)
        mc.stop()
        history = mc.history()
        assert len(history) >= 1
        # At least one bucket should have our data
        total_tokens = sum(b.tokens_in for b in history) + mc.snapshot().tokens_in
        assert total_tokens == 7
