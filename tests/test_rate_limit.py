"""Tests for the in-process rate limiter."""

from cairn.api.rate_limit import _SlidingWindow


class TestSlidingWindow:

    def test_allows_within_limit(self):
        w = _SlidingWindow()
        for _ in range(5):
            assert w.is_allowed("client1", max_requests=5, window_seconds=60)

    def test_blocks_over_limit(self):
        w = _SlidingWindow()
        for _ in range(3):
            assert w.is_allowed("client1", max_requests=3, window_seconds=60)
        assert not w.is_allowed("client1", max_requests=3, window_seconds=60)

    def test_separate_keys(self):
        w = _SlidingWindow()
        for _ in range(3):
            w.is_allowed("client1", max_requests=3, window_seconds=60)
        # Different key should still be allowed
        assert w.is_allowed("client2", max_requests=3, window_seconds=60)

    def test_cleanup_removes_stale(self):
        w = _SlidingWindow()
        w._requests["old_key"] = []  # Empty = stale
        w.cleanup(max_age=0)
        assert "old_key" not in w._requests

    def test_expired_entries_pruned(self):
        import time
        w = _SlidingWindow()
        # Fill to limit
        for _ in range(3):
            assert w.is_allowed("client1", max_requests=3, window_seconds=0.1)
        assert not w.is_allowed("client1", max_requests=3, window_seconds=0.1)
        # Wait for window to expire
        time.sleep(0.15)
        # Should be allowed again
        assert w.is_allowed("client1", max_requests=3, window_seconds=0.1)
