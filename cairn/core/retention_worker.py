"""RetentionWorker — background thread that runs retention policies on schedule.

Follows the same thread lifecycle pattern as AlertEvaluator and WebhookDeliveryWorker.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.config import RetentionConfig
    from cairn.core.retention import RetentionManager

logger = logging.getLogger(__name__)


class RetentionWorker:
    """Background thread that periodically executes retention policies."""

    def __init__(self, retention_manager: RetentionManager, config: RetentionConfig):
        self.retention_manager = retention_manager
        self.config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the retention scan loop in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="RetentionWorker",
        )
        self._thread.start()
        logger.info(
            "RetentionWorker: started (interval=%dh, dry_run=%s)",
            self.config.scan_interval_hours,
            self.config.dry_run,
        )

    def stop(self) -> None:
        """Signal stop and wait for the thread to finish."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.warning("RetentionWorker: thread did not stop within timeout")
        else:
            logger.info("RetentionWorker: stopped")
        self._thread = None

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception:
                logger.warning("RetentionWorker: scan cycle failed", exc_info=True)
            self._stop_event.wait(timeout=self.config.scan_interval_hours * 3600)

    def _poll(self) -> None:
        """Run all active retention policies."""
        results = self.retention_manager.run_cleanup(dry_run=self.config.dry_run)
        if not results:
            return

        total = 0
        for r in results:
            if r.get("dry_run"):
                count = r.get("would_delete", 0)
                if count > 0:
                    logger.info(
                        "RetentionWorker: [dry-run] policy %d (%s) would delete %d rows",
                        r["policy_id"], r["resource_type"], count,
                    )
            elif r.get("reason") == "legal_hold":
                logger.debug(
                    "RetentionWorker: policy %d (%s) skipped — legal hold",
                    r["policy_id"], r["resource_type"],
                )
            else:
                deleted = r.get("deleted", 0)
                total += deleted
                if deleted > 0:
                    logger.info(
                        "RetentionWorker: policy %d (%s) deleted %d rows",
                        r["policy_id"], r["resource_type"], deleted,
                    )

        if total > 0:
            logger.info("RetentionWorker: scan complete — %d total rows deleted", total)
