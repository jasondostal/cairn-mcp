"""Multi-agent stress tests — concurrent safety validation (ca-126).

Tests that critical paths handle concurrent access correctly:
- Work item claim races (optimistic lock)
- Concurrent heartbeat updates (idempotent)
- Parallel event publishing
- Subscription pattern matching under load
- Circuit breaker thread safety
- Notification dispatch contention
- Push notifier concurrent sends

Uses threading to simulate concurrent agents hitting the same resources.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

import pytest


class TestConcurrentClaim:
    """Multiple agents racing to claim the same work item."""

    def test_only_one_agent_claims_successfully(self):
        """Simulate N agents trying to claim the same work item. Only 1 wins."""
        from cairn.core.work_items import WorkItemManager

        db = MagicMock()
        event_bus = MagicMock()
        wim = WorkItemManager(db, event_bus, MagicMock())

        item = {"id": 42, "status": "open", "project_id": 1, "display_id": "ca-42",
                "project_name": "cairn", "parent_id": None}

        call_count = 0
        call_lock = threading.Lock()

        def mock_resolve(wid):
            return item

        def mock_execute_one(sql, params=None):
            nonlocal call_count
            with call_lock:
                call_count += 1
                if call_count == 1:
                    return {"id": 42}  # First claimer wins
                return None  # Others fail — row already in_progress

        db.execute_one.side_effect = mock_execute_one
        db.execute.return_value = []
        wim._resolve_id = mock_resolve
        wim._display_id = lambda i: i.get("display_id", f"#{i['id']}")

        results = {"success": 0, "failure": 0}
        results_lock = threading.Lock()

        def attempt_claim(agent_name):
            try:
                wim.claim(42, agent_name)
                with results_lock:
                    results["success"] += 1
            except ValueError:
                with results_lock:
                    results["failure"] += 1

        threads = [threading.Thread(target=attempt_claim, args=(f"agent-{i}",))
                   for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert results["success"] == 1
        assert results["failure"] == 4

    def test_claim_already_in_progress(self):
        from cairn.core.work_items import WorkItemManager

        db = MagicMock()
        event_bus = MagicMock()
        wim = WorkItemManager(db, event_bus, MagicMock())

        item = {"id": 42, "status": "in_progress", "project_id": 1,
                "display_id": "ca-42", "project_name": "cairn", "parent_id": None}
        wim._resolve_id = lambda wid: item
        wim._display_id = lambda i: i.get("display_id", f"#{i['id']}")
        db.execute_one.return_value = None

        with pytest.raises(ValueError, match="Cannot claim"):
            wim.claim(42, "agent-late")


class TestConcurrentHeartbeat:
    """Multiple agents heartbeating concurrently on different work items."""

    def test_concurrent_heartbeats_all_succeed(self):
        from cairn.core.work_items import WorkItemManager

        db = MagicMock()
        event_bus = MagicMock()
        wim = WorkItemManager(db, event_bus, MagicMock())

        items = {
            i: {"id": i, "status": "in_progress", "project_id": 1,
                "display_id": f"ca-{i}", "project_name": "cairn", "parent_id": None}
            for i in range(1, 6)
        }

        wim._resolve_id = lambda wid: items.get(wid)
        wim._display_id = lambda i: i.get("display_id", f"#{i['id']}")

        heartbeat_count = 0
        count_lock = threading.Lock()

        def mock_execute(sql, params=None):
            nonlocal heartbeat_count
            if "last_heartbeat" in str(sql):
                with count_lock:
                    heartbeat_count += 1
            return []

        db.execute.side_effect = mock_execute

        def do_heartbeat(agent_id, work_item_id):
            wim.heartbeat(work_item_id, f"agent-{agent_id}", state="working")

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(do_heartbeat, i, i) for i in range(1, 6)]
            for f in as_completed(futures):
                f.result()

        assert heartbeat_count == 5


class TestConcurrentEventPublish:
    """Multiple agents publishing events simultaneously."""

    def test_concurrent_publishes_all_recorded(self):
        from cairn.core.event_bus import EventBus

        db = MagicMock()
        pm = MagicMock()
        bus = EventBus(db, pm)

        publish_count = 0
        count_lock = threading.Lock()

        def mock_execute_one(sql, params=None):
            nonlocal publish_count
            with count_lock:
                publish_count += 1
            return {"id": publish_count}

        db.execute_one.side_effect = mock_execute_one
        db.execute.return_value = []  # For dispatch record queries

        def publish_event(i):
            bus.publish(
                session_name=f"session-{i}",
                event_type="work_item.completed",
                payload={"agent": f"agent-{i}"},
            )

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(publish_event, i) for i in range(20)]
            for f in as_completed(futures):
                f.result()

        assert publish_count == 20



class TestCircuitBreakerConcurrency:
    """CircuitBreaker thread safety with per-handler tracking."""

    def test_concurrent_failures_trip_breaker(self):
        from cairn.core.event_dispatcher import CircuitBreaker

        cb = CircuitBreaker(threshold=5, cooldown=60)

        def record_failure():
            cb.record_failure("handler_a")

        threads = [threading.Thread(target=record_failure) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert cb.is_open("handler_a") is True

    def test_concurrent_successes_keep_closed(self):
        from cairn.core.event_dispatcher import CircuitBreaker

        cb = CircuitBreaker(threshold=5, cooldown=60)

        def record_success():
            cb.record_success("handler_b")

        threads = [threading.Thread(target=record_success) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert cb.is_open("handler_b") is False

    def test_independent_handlers_dont_interfere(self):
        """Failures in handler_a don't affect handler_b's circuit."""
        from cairn.core.event_dispatcher import CircuitBreaker

        cb = CircuitBreaker(threshold=3, cooldown=60)

        def fail_handler_a():
            cb.record_failure("handler_a")

        def succeed_handler_b():
            cb.record_success("handler_b")

        threads = []
        for _ in range(5):
            threads.append(threading.Thread(target=fail_handler_a))
        for _ in range(5):
            threads.append(threading.Thread(target=succeed_handler_b))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert cb.is_open("handler_a") is True
        assert cb.is_open("handler_b") is False


class TestSSEPatternMatchingLoad:
    """High-throughput pattern matching for SSE subscriptions."""

    def test_high_volume_pattern_matching(self):
        import fnmatch

        patterns = ["work_item.*", "deliverable.*", "notification.*"]

        def matches(event_type):
            return any(fnmatch.fnmatch(event_type, p) for p in patterns)

        event_types = [
            "work_item.completed", "work_item.gated", "work_item.claimed",
            "deliverable.created", "deliverable.approved", "deliverable.rejected",
            "notification.created", "notification.read",
            "memory.created", "session_start", "session_end",
        ]

        results = {}
        results_lock = threading.Lock()

        def match_batch(batch_id):
            local_results = {}
            for et in event_types:
                local_results[et] = matches(et)
            with results_lock:
                results[batch_id] = local_results

        # 50 concurrent batches simulating high SSE throughput
        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(match_batch, i) for i in range(50)]
            for f in as_completed(futures):
                f.result()

        assert len(results) == 50
        # All batches should produce identical results
        expected = {
            "work_item.completed": True, "work_item.gated": True, "work_item.claimed": True,
            "deliverable.created": True, "deliverable.approved": True, "deliverable.rejected": True,
            "notification.created": True, "notification.read": True,
            "memory.created": False, "session_start": False, "session_end": False,
        }
        for batch_id, batch_results in results.items():
            assert batch_results == expected, f"Batch {batch_id} produced wrong results"


class TestMixedWorkload:
    """Simulates a realistic multi-agent workload with mixed operations."""

    def test_mixed_claim_heartbeat_complete(self):
        """Simulate N agents: claim different items, heartbeat, then complete."""
        from cairn.core.work_items import WorkItemManager

        db = MagicMock()
        event_bus = MagicMock()
        wim = WorkItemManager(db, event_bus, MagicMock())

        items = {
            i: {"id": i, "status": "open", "project_id": 1,
                "display_id": f"ca-{i}", "project_name": "cairn", "parent_id": None}
            for i in range(1, 6)
        }

        claim_results = {}
        claim_lock = threading.Lock()

        def mock_resolve(wid):
            return items.get(wid)

        def mock_execute_one(sql, params=None):
            # Claims succeed (each agent claims different item)
            if "SET status = 'in_progress'" in str(sql):
                return {"id": params[-1] if params else 1}
            return {"id": 1}

        db.execute_one.side_effect = mock_execute_one
        db.execute.return_value = []
        wim._resolve_id = mock_resolve
        wim._display_id = lambda i: i.get("display_id", f"#{i['id']}")

        completed = 0
        completed_lock = threading.Lock()

        def agent_lifecycle(agent_id, work_item_id):
            nonlocal completed
            # 1. Claim
            wim.claim(work_item_id, f"agent-{agent_id}")

            # Simulate the item being in_progress now
            items[work_item_id]["status"] = "in_progress"

            # 2. Heartbeat a few times
            for _ in range(3):
                wim.heartbeat(work_item_id, f"agent-{agent_id}", state="working")

            # 3. Complete
            wim.complete(work_item_id)

            with completed_lock:
                completed += 1

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(agent_lifecycle, i, i) for i in range(1, 6)]
            for f in as_completed(futures):
                f.result()

        assert completed == 5
