"""Tests for the DecayWorker controlled forgetting system."""

from unittest.mock import MagicMock

from cairn.config import DecayConfig
from cairn.core.decay import DecayWorker


class TestDecayWorker:

    def _make_worker(self, *, dry_run=True, enabled=True, threshold=0.05):
        db = MagicMock()
        config = DecayConfig(
            enabled=enabled,
            dry_run=dry_run,
            threshold=threshold,
            min_age_days=90,
            protect_importance=0.8,
            protect_types=("rule",),
            scan_interval_hours=24,
        )
        return DecayWorker(db, config, decay_lambda=0.01), db

    def test_dry_run_does_not_inactivate(self):
        worker, db = self._make_worker(dry_run=True)
        db.execute.return_value = [
            {"id": 1, "memory_type": "note", "importance": 0.3,
             "access_count": 0, "last_accessed_at": None,
             "updated_at": None, "created_at": None, "decay_score": 0.01},
        ]
        result = worker.scan()
        assert result["dry_run"] is True
        assert result["inactivated"] == 0
        assert 1 in result["candidates"]
        db.commit.assert_not_called()

    def test_live_mode_inactivates(self):
        worker, db = self._make_worker(dry_run=False)
        # First call returns candidates, second is the UPDATE
        db.execute.side_effect = [
            [{"id": 1, "memory_type": "note", "importance": 0.3,
              "access_count": 0, "last_accessed_at": None,
              "updated_at": None, "created_at": None, "decay_score": 0.01}],
            None,  # UPDATE result
        ]
        result = worker.scan()
        assert result["dry_run"] is False
        assert result["inactivated"] == 1
        db.commit.assert_called_once()

    def test_no_candidates_returns_zero(self):
        worker, db = self._make_worker()
        db.execute.return_value = []
        result = worker.scan()
        assert result["scanned"] == 0
        assert result["inactivated"] == 0

    def test_disabled_worker_does_not_start(self):
        worker, _ = self._make_worker(enabled=False)
        worker.start()
        assert worker._thread is None

    def test_enabled_worker_starts_thread(self):
        worker, _ = self._make_worker(enabled=True)
        worker.start()
        assert worker._thread is not None
        assert worker._thread.daemon is True
        worker.stop()

    def test_inactivated_ids_in_live_result(self):
        worker, db = self._make_worker(dry_run=False)
        db.execute.side_effect = [
            [{"id": 5, "memory_type": "note", "importance": 0.2,
              "access_count": 0, "last_accessed_at": None,
              "updated_at": None, "created_at": None, "decay_score": 0.02},
             {"id": 9, "memory_type": "learning", "importance": 0.4,
              "access_count": 1, "last_accessed_at": None,
              "updated_at": None, "created_at": None, "decay_score": 0.03}],
            None,
        ]
        result = worker.scan()
        assert result["inactivated"] == 2
        assert set(result["inactivated_ids"]) == {5, 9}
