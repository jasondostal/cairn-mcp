"""Tests for cairn.core.stats — EventBusStats thread-safe counters."""

from cairn.core.stats import EventBusStats, init_event_bus_stats
import cairn.core.stats as stats_module


class TestEventBusStats:
    def test_initial_state(self):
        s = EventBusStats()
        assert s.health == "unknown"
        d = s.to_dict()
        assert d["events_published"] == 0
        assert d["events_by_type"] == {}
        assert d["sessions_opened"] == 0
        assert d["sessions_closed"] == 0
        assert d["sse"]["connections_active"] == 0
        assert d["sse"]["connections_total"] == 0
        assert d["sse"]["events_streamed"] == 0
        assert d["errors"] == 0
        assert d["last_event_at"] is None
        assert d["uptime_seconds"] >= 0

    def test_record_publish(self):
        s = EventBusStats()
        s.record_publish("tool_use")
        s.record_publish("tool_use")
        s.record_publish("session_start")
        d = s.to_dict()
        assert d["events_published"] == 3
        assert d["events_by_type"] == {"tool_use": 2, "session_start": 1}
        assert d["last_event_at"] is not None
        assert d["health"] == "healthy"

    def test_record_sessions(self):
        s = EventBusStats()
        s.record_session_opened()
        s.record_session_opened()
        s.record_session_closed()
        d = s.to_dict()
        assert d["sessions_opened"] == 2
        assert d["sessions_closed"] == 1

    def test_sse_connect_disconnect(self):
        s = EventBusStats()
        s.record_sse_connect()
        s.record_sse_connect()
        assert s.to_dict()["sse"]["connections_active"] == 2
        assert s.to_dict()["sse"]["connections_total"] == 2
        s.record_sse_disconnect()
        assert s.to_dict()["sse"]["connections_active"] == 1
        assert s.to_dict()["sse"]["connections_total"] == 2

    def test_sse_disconnect_floor_zero(self):
        s = EventBusStats()
        s.record_sse_disconnect()
        assert s.to_dict()["sse"]["connections_active"] == 0

    def test_sse_events_streamed(self):
        s = EventBusStats()
        s.record_sse_event()
        s.record_sse_event()
        s.record_sse_event()
        assert s.to_dict()["sse"]["events_streamed"] == 3

    def test_error_tracking(self):
        s = EventBusStats()
        s.record_publish("tool_use")
        s.record_error("connection refused")
        d = s.to_dict()
        assert d["errors"] == 1
        assert d["last_error"] is not None
        assert d["last_error_msg"] == "connection refused"
        assert d["health"] == "degraded"

    def test_unhealthy_after_3_consecutive_errors(self):
        s = EventBusStats()
        s.record_error("e1")
        s.record_error("e2")
        s.record_error("e3")
        assert s.health == "unhealthy"

    def test_healthy_after_window_clears(self):
        s = EventBusStats()
        s.record_error("old")
        # Push 10 successes to fill the window (maxlen=10)
        for _ in range(10):
            s.record_publish("tool_use")
        assert s.health == "healthy"

    def test_to_dict_no_deadlock(self):
        """to_dict calls health property — both acquire lock. RLock prevents deadlock."""
        s = EventBusStats()
        s.record_publish("session_start")
        d = s.to_dict()
        assert d["health"] == "healthy"
        assert "uptime_seconds" in d


class TestEventBusStatsSingleton:
    def test_init_event_bus_stats(self):
        result = init_event_bus_stats()
        assert result is stats_module.event_bus_stats
        assert isinstance(result, EventBusStats)

    def test_reinit_replaces_singleton(self):
        first = init_event_bus_stats()
        first.record_publish("tool_use")
        second = init_event_bus_stats()
        assert second is not first
        assert second.to_dict()["events_published"] == 0
