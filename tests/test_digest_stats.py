"""Test DigestStats: thread safety, health transitions, avg latency, queue depth."""

import threading

from cairn.core.stats import DigestStats


# ── Basic recording ───────────────────────────────────────────


def test_record_batch():
    """record_batch should increment counters and update timing."""
    ds = DigestStats()
    ds.record_batch(events=10, duration=2.5)

    d = ds.to_dict()
    assert d["batches_processed"] == 1
    assert d["events_digested"] == 10
    assert d["avg_latency_s"] == 2.5
    assert d["last_batch_time"] is not None


def test_record_failure():
    """record_failure should increment failure counter and record message."""
    ds = DigestStats()
    ds.record_failure("LLM timeout")

    d = ds.to_dict()
    assert d["batches_failed"] == 1
    assert d["last_error"] is not None
    assert d["last_error_msg"] == "LLM timeout"


# ── Health transitions ────────────────────────────────────────


def test_health_idle_initially():
    """Fresh DigestStats should report 'idle' health."""
    ds = DigestStats()
    assert ds.health == "idle"


def test_health_healthy_after_success():
    """After a successful batch, health should be 'healthy'."""
    ds = DigestStats()
    ds.record_batch(5, 1.0)
    assert ds.health == "healthy"


def test_health_degraded_after_one_failure():
    """Any failure in the window should make health 'degraded'."""
    ds = DigestStats()
    ds.record_batch(5, 1.0)
    ds.record_failure("test error")
    assert ds.health == "degraded"


def test_health_backoff_after_three_consecutive_failures():
    """3+ consecutive failures should make health 'backoff'."""
    ds = DigestStats()
    ds.record_failure("err 1")
    ds.record_failure("err 2")
    ds.record_failure("err 3")
    assert ds.health == "backoff"


def test_health_recovers_after_success():
    """A success after failures should bring health back to degraded (not backoff)."""
    ds = DigestStats()
    ds.record_failure("err 1")
    ds.record_failure("err 2")
    ds.record_failure("err 3")
    assert ds.health == "backoff"
    ds.record_batch(5, 1.0)
    assert ds.health == "degraded"  # still has failures in window


# ── Avg latency ───────────────────────────────────────────────


def test_avg_latency_none_when_no_batches():
    """avg_latency should be None before any batches."""
    ds = DigestStats()
    assert ds.avg_latency is None


def test_avg_latency_calculation():
    """avg_latency should be total_time / batches_processed."""
    ds = DigestStats()
    ds.record_batch(10, 2.0)
    ds.record_batch(10, 4.0)
    assert ds.avg_latency == 3.0


# ── Queue depth ───────────────────────────────────────────────


def test_queue_depth():
    """set_queue_depth should update the queue depth."""
    ds = DigestStats()
    ds.set_queue_depth(7)
    assert ds.to_dict()["queue_depth"] == 7


# ── State ─────────────────────────────────────────────────────


def test_state_tracking():
    """set_state should update the state field."""
    ds = DigestStats()
    assert ds.to_dict()["state"] == "idle"
    ds.set_state("processing")
    assert ds.to_dict()["state"] == "processing"


# ── Thread safety ─────────────────────────────────────────────


def test_thread_safety():
    """Concurrent record_batch calls should not lose data."""
    ds = DigestStats()
    iterations = 100

    def worker():
        for _ in range(iterations):
            ds.record_batch(1, 0.01)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert ds.to_dict()["batches_processed"] == 400
    assert ds.to_dict()["events_digested"] == 400


# ── to_dict completeness ─────────────────────────────────────


def test_to_dict_keys():
    """to_dict should include all expected keys."""
    ds = DigestStats()
    d = ds.to_dict()
    expected_keys = {
        "health", "state", "batches_processed", "batches_failed",
        "events_digested", "queue_depth", "avg_latency_s",
        "last_batch_time", "last_error", "last_error_msg",
    }
    assert set(d.keys()) == expected_keys
