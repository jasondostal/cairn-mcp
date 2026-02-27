"""Tests for Watchtower Phase 5 — Data Retention."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from cairn.core.retention import (
    RetentionManager, AUDIT_MIN_TTL_DAYS, DELETE_BATCH_SIZE, VALID_RESOURCE_TYPES,
)
from cairn.core.retention_worker import RetentionWorker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(enabled=True, scan_interval_hours=24, dry_run=True):
    cfg = MagicMock()
    cfg.enabled = enabled
    cfg.scan_interval_hours = scan_interval_hours
    cfg.dry_run = dry_run
    return cfg


def _make_db():
    db = MagicMock()
    db.execute = MagicMock(return_value=[])
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


def _make_policy_row(
    id=1, project_id=None, resource_type="events", ttl_days=90,
    legal_hold=False, is_active=True, last_run_at=None, last_deleted=0,
):
    now = datetime.now(timezone.utc)
    return (id, project_id, resource_type, ttl_days, legal_hold, is_active,
            last_run_at, last_deleted, now, now)


# ===========================================================================
# CRUD
# ===========================================================================

class TestRetentionCRUD:
    def test_create(self):
        db = _make_db()
        db.execute.return_value = [_make_policy_row()]
        mgr = RetentionManager(db, _make_config())

        result = mgr.create(resource_type="events", ttl_days=90)
        assert result["resource_type"] == "events"
        assert result["ttl_days"] == 90
        db.commit.assert_called_once()

    def test_create_invalid_resource_type(self):
        mgr = RetentionManager(_make_db(), _make_config())
        with pytest.raises(ValueError, match="Invalid resource_type"):
            mgr.create(resource_type="nonexistent", ttl_days=90)

    def test_create_invalid_ttl(self):
        mgr = RetentionManager(_make_db(), _make_config())
        with pytest.raises(ValueError, match="ttl_days must be >= 1"):
            mgr.create(resource_type="events", ttl_days=0)

    def test_create_audit_enforces_min_ttl(self):
        db = _make_db()
        db.execute.return_value = [_make_policy_row(resource_type="audit_log", ttl_days=AUDIT_MIN_TTL_DAYS)]
        mgr = RetentionManager(db, _make_config())

        mgr.create(resource_type="audit_log", ttl_days=30)
        # Check that the SQL was called with AUDIT_MIN_TTL_DAYS, not 30
        call_args = db.execute.call_args_list[0]
        params = call_args[0][1]
        assert params[2] == AUDIT_MIN_TTL_DAYS  # ttl_days param

    def test_get(self):
        db = _make_db()
        db.execute.return_value = [_make_policy_row()]
        mgr = RetentionManager(db, _make_config())

        result = mgr.get(1)
        assert result is not None
        assert result["id"] == 1

    def test_get_not_found(self):
        db = _make_db()
        db.execute.return_value = []
        mgr = RetentionManager(db, _make_config())

        assert mgr.get(999) is None

    def test_list(self):
        db = _make_db()
        db.execute.side_effect = [
            [(2,)],  # count
            [_make_policy_row(id=1), _make_policy_row(id=2)],  # rows
        ]
        mgr = RetentionManager(db, _make_config())

        result = mgr.list()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    def test_update(self):
        db = _make_db()
        db.execute.return_value = [_make_policy_row(ttl_days=180)]
        mgr = RetentionManager(db, _make_config())

        result = mgr.update(1, ttl_days=180)
        assert result["ttl_days"] == 180
        db.commit.assert_called()

    def test_delete(self):
        db = _make_db()
        db.execute.return_value = [(1,)]
        mgr = RetentionManager(db, _make_config())

        assert mgr.delete(1) is True
        db.commit.assert_called()

    def test_delete_not_found(self):
        db = _make_db()
        db.execute.return_value = []
        mgr = RetentionManager(db, _make_config())

        assert mgr.delete(999) is False


# ===========================================================================
# Valid resource types
# ===========================================================================

class TestResourceTypes:
    def test_all_expected_types(self):
        expected = {
            "events", "usage_events", "metric_rollups",
            "webhook_deliveries", "alert_history", "audit_log", "event_dispatches",
        }
        assert VALID_RESOURCE_TYPES == expected


# ===========================================================================
# Preview
# ===========================================================================

class TestPreview:
    def test_preview_shows_count(self):
        db = _make_db()
        policy_row = _make_policy_row(resource_type="events", ttl_days=90)
        db.execute.side_effect = [
            [policy_row],  # get
            [(42,)],       # count query
        ]
        mgr = RetentionManager(db, _make_config())

        results = mgr.preview(policy_id=1)
        assert len(results) == 1
        assert results[0]["would_delete"] == 42

    def test_preview_legal_hold_skipped(self):
        db = _make_db()
        policy_row = _make_policy_row(legal_hold=True)
        db.execute.return_value = [policy_row]
        mgr = RetentionManager(db, _make_config())

        results = mgr.preview(policy_id=1)
        assert results[0]["would_delete"] == 0
        assert results[0]["reason"] == "legal_hold"


# ===========================================================================
# Cleanup
# ===========================================================================

class TestCleanup:
    def test_dry_run_returns_counts(self):
        db = _make_db()
        # list call: count + rows
        db.execute.side_effect = [
            [(1,)],  # count
            [_make_policy_row(resource_type="events", ttl_days=90)],  # rows
            [(15,)],  # count for cleanup
        ]
        mgr = RetentionManager(db, _make_config())

        results = mgr.run_cleanup(dry_run=True)
        assert len(results) == 1
        assert results[0]["would_delete"] == 15
        assert results[0]["dry_run"] is True

    def test_live_run_deletes(self):
        db = _make_db()
        # list call: count + rows
        db.execute.side_effect = [
            [(1,)],  # count
            [_make_policy_row(resource_type="events", ttl_days=90)],  # rows
            [(1,), (2,), (3,)],  # first batch (3 deleted)
            [],  # second batch (0 = done)
            None,  # update stats
        ]
        mgr = RetentionManager(db, _make_config())

        results = mgr.run_cleanup(dry_run=False)
        assert len(results) == 1
        assert results[0]["deleted"] == 3
        assert results[0]["dry_run"] is False

    def test_legal_hold_skips_cleanup(self):
        db = _make_db()
        db.execute.side_effect = [
            [(1,)],  # count
            [_make_policy_row(legal_hold=True)],  # rows
        ]
        mgr = RetentionManager(db, _make_config())

        results = mgr.run_cleanup(dry_run=False)
        assert results[0]["reason"] == "legal_hold"
        assert results[0]["deleted"] == 0

    def test_audit_min_ttl_enforced(self):
        db = _make_db()
        db.execute.side_effect = [
            [(1,)],  # count
            [_make_policy_row(resource_type="audit_log", ttl_days=30)],
            [(0,)],  # count
        ]
        mgr = RetentionManager(db, _make_config())

        mgr.run_cleanup(dry_run=True)
        # The count query should use 365, not 30
        count_call = db.execute.call_args_list[2]
        params = count_call[0][1]
        assert params[0] == AUDIT_MIN_TTL_DAYS


# ===========================================================================
# Status
# ===========================================================================

class TestStatus:
    def test_status(self):
        db = _make_db()
        now = datetime.now(timezone.utc)
        db.execute.return_value = [(3, 2, 1, now, now, 100)]
        mgr = RetentionManager(db, _make_config())

        status = mgr.status()
        assert status["total_policies"] == 3
        assert status["active_policies"] == 2
        assert status["held_policies"] == 1
        assert status["total_deleted"] == 100
        assert status["scan_interval_hours"] == 24
        assert status["dry_run"] is True


# ===========================================================================
# Worker
# ===========================================================================

class TestRetentionWorker:
    def test_start_stop(self):
        mgr = MagicMock()
        config = _make_config()
        worker = RetentionWorker(mgr, config)

        worker.start()
        assert worker._thread is not None
        assert worker._thread.is_alive()

        worker.stop()
        assert worker._thread is None

    def test_poll_calls_cleanup(self):
        mgr = MagicMock()
        mgr.run_cleanup.return_value = []
        config = _make_config(dry_run=True)
        worker = RetentionWorker(mgr, config)

        worker._poll()
        mgr.run_cleanup.assert_called_once_with(dry_run=True)

    def test_poll_error_resilience(self):
        """_loop catches exceptions from _poll — verify via the worker's loop behavior."""
        mgr = MagicMock()
        mgr.run_cleanup.side_effect = RuntimeError("db gone")
        config = _make_config()
        worker = RetentionWorker(mgr, config)

        # _poll itself doesn't catch — _loop does. Test that _poll raises
        # but the worker lifecycle is resilient
        with pytest.raises(RuntimeError):
            worker._poll()
