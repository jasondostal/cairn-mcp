"""Controlled forgetting — background worker that auto-inactivates decayed memories.

Follows the same daemon thread pattern as RollupWorker and EventDispatcher:
- Polls at configurable interval (default 24h)
- Exponential backoff on errors
- Daemon thread (exits with main process)
- Dry-run mode for safety

Decay score: e^(-lambda * days_since_last_access)
where last_access = COALESCE(last_accessed_at, updated_at)

Protected classes (never forgotten):
- Rules (memory_type = 'rule')
- High-importance memories (importance >= protect_importance)
- Recently-created memories (created_at within min_age_days)
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.config import DecayConfig
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class DecayWorker:
    """Background thread that scans for and inactivates decayed memories."""

    MAX_BACKOFF = 3600.0  # 1 hour max between retries on error

    def __init__(self, db: Database, config: DecayConfig, decay_lambda: float = 0.01):
        self.db = db
        self.config = config
        self.decay_lambda = decay_lambda
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.config.enabled:
            logger.info("DecayWorker: disabled (CAIRN_DECAY_ENABLED=false)")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="DecayWorker",
        )
        self._thread.start()
        mode = "DRY RUN" if self.config.dry_run else "LIVE"
        logger.info(
            "DecayWorker: started (%s, interval=%dh, threshold=%.3f, lambda=%.4f)",
            mode, self.config.scan_interval_hours, self.config.threshold,
            self.decay_lambda,
        )

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.warning("DecayWorker: thread did not stop within timeout")
        else:
            logger.info("DecayWorker: stopped")
        self._thread = None

    def _run_loop(self) -> None:
        poll_interval = self.config.scan_interval_hours * 3600.0
        while not self._stop_event.is_set():
            try:
                self._scan()
                poll_interval = self.config.scan_interval_hours * 3600.0
            except Exception:
                logger.warning("DecayWorker: scan failed", exc_info=True)
                poll_interval = min(poll_interval * 2, self.MAX_BACKOFF)
            self._stop_event.wait(timeout=poll_interval)

    def scan(self) -> dict:
        """Public scan method for dry-run testing and MCP exposure."""
        return self._scan()

    def _scan(self) -> dict:
        """Find and optionally inactivate memories below the decay threshold."""
        protect_types_placeholder = ",".join(
            ["%s"] * len(self.config.protect_types)
        )

        rows = self.db.execute(
            f"""
            SELECT m.id, m.memory_type, m.importance, m.access_count,
                   m.last_accessed_at, m.updated_at, m.created_at,
                   EXP(
                       -%s * EXTRACT(EPOCH FROM (
                           NOW() - COALESCE(m.last_accessed_at, m.updated_at)
                       )) / 86400.0
                   ) as decay_score
            FROM memories m
            WHERE m.is_active = true
              AND m.created_at < NOW() - make_interval(days => %s)
              AND m.importance < %s
              AND m.memory_type NOT IN ({protect_types_placeholder})
              AND EXP(
                  -%s * EXTRACT(EPOCH FROM (
                      NOW() - COALESCE(m.last_accessed_at, m.updated_at)
                  )) / 86400.0
              ) < %s
            ORDER BY EXP(
                -%s * EXTRACT(EPOCH FROM (
                    NOW() - COALESCE(m.last_accessed_at, m.updated_at)
                )) / 86400.0
            ) ASC
            LIMIT 100
            """,
            (
                self.decay_lambda,
                self.config.min_age_days,
                self.config.protect_importance,
                *self.config.protect_types,
                self.decay_lambda,
                self.config.threshold,
                self.decay_lambda,
            ),
        )

        if not rows:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.debug("DecayWorker: no candidates found")
            return {"scanned": 0, "inactivated": 0, "dry_run": self.config.dry_run}

        candidate_ids = [r["id"] for r in rows]

        if self.config.dry_run:
            try:
                self.db.rollback()
            except Exception:
                pass
            for r in rows:
                logger.info(
                    "DecayWorker [DRY RUN]: would inactivate memory #%d "
                    "(type=%s, importance=%.2f, access_count=%d, decay=%.4f)",
                    r["id"], r["memory_type"], r["importance"],
                    r["access_count"], r["decay_score"],
                )
            return {
                "scanned": len(candidate_ids),
                "inactivated": 0,
                "dry_run": True,
                "candidates": candidate_ids,
            }

        # LIVE mode: inactivate
        placeholders = ",".join(["%s"] * len(candidate_ids))
        self.db.execute(
            f"""
            UPDATE memories
            SET is_active = false,
                inactive_reason = 'decay',
                updated_at = NOW()
            WHERE id IN ({placeholders})
            """,
            tuple(candidate_ids),
        )
        self.db.commit()

        logger.info(
            "DecayWorker: inactivated %d memories (decay threshold=%.3f)",
            len(candidate_ids), self.config.threshold,
        )
        return {
            "scanned": len(candidate_ids),
            "inactivated": len(candidate_ids),
            "dry_run": False,
            "inactivated_ids": candidate_ids,
        }
