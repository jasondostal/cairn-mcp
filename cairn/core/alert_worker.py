"""AlertEvaluator — background thread that evaluates alert rules on a schedule.

Polls active rules at a configurable interval, evaluates conditions against
metric_rollups and health stats, records alerts, and fires webhooks for delivery.

Follows the same thread lifecycle pattern as WebhookDeliveryWorker and DecayWorker.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cairn.core.alerting import AlertManager

if TYPE_CHECKING:
    from cairn.config import AlertingConfig
    from cairn.core.webhooks import WebhookManager
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class AlertEvaluator:
    """Background thread that evaluates alert rules and fires webhooks."""

    def __init__(
        self,
        db: Database,
        alert_manager: AlertManager,
        webhook_manager: WebhookManager | None,
        config: AlertingConfig,
    ):
        self.db = db
        self.alert_manager = alert_manager
        self.webhook_manager = webhook_manager
        self.config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the evaluation loop in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="AlertEvaluator",
        )
        self._thread.start()
        logger.info(
            "AlertEvaluator: started (interval=%ds)",
            self.config.eval_interval_seconds,
        )

    def stop(self) -> None:
        """Signal stop and wait for the thread to finish."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.warning("AlertEvaluator: thread did not stop within timeout")
        else:
            logger.info("AlertEvaluator: stopped")
        self._thread = None

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception:
                logger.warning("AlertEvaluator: poll cycle failed", exc_info=True)
            self._stop_event.wait(timeout=self.config.eval_interval_seconds)

    def _poll(self) -> None:
        """Fetch eligible rules and evaluate each one."""
        # Get active rules whose cooldown has expired
        rows = self.db.execute(
            """
            SELECT id, name, condition_type, condition, notification, severity,
                   is_active, cooldown_minutes, last_fired_at, created_at, updated_at
            FROM alert_rules
            WHERE is_active = true
              AND (last_fired_at IS NULL
                   OR last_fired_at < NOW() - make_interval(mins => cooldown_minutes))
            ORDER BY id ASC
            """,
        )

        if not rows:
            self.db.rollback()  # release connection from read-only query
            return

        fired = 0
        for row in rows:
            rule = AlertManager._row_to_dict(row)
            try:
                result = self.alert_manager.evaluate_rule(rule)
            except Exception:
                logger.warning(
                    "AlertEvaluator: evaluation failed for rule %d ('%s')",
                    rule["id"], rule["name"], exc_info=True,
                )
                continue

            if result is None:
                continue

            # Alert triggered — record and optionally deliver via webhook
            delivered = False
            notification = rule.get("notification") or {}
            webhook_id = notification.get("webhook_id")

            if webhook_id and self.webhook_manager:
                try:
                    payload = {
                        "event_type": "alert.fired",
                        "alert_rule_id": rule["id"],
                        "alert_rule_name": rule["name"],
                        "severity": rule["severity"],
                        "message": result["message"],
                        "context": result.get("context", {}),
                        "fired_at": datetime.now(timezone.utc).isoformat(),
                    }
                    self.webhook_manager.create_delivery(
                        webhook_id=webhook_id,
                        event_id=0,  # no associated event
                        request_body=payload,
                    )
                    delivered = True
                except Exception:
                    logger.warning(
                        "AlertEvaluator: webhook delivery creation failed for rule %d",
                        rule["id"], exc_info=True,
                    )

            try:
                self.alert_manager.record_alert(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    message=result["message"],
                    context=result.get("context"),
                    delivered=delivered,
                )
                fired += 1
            except Exception:
                logger.warning(
                    "AlertEvaluator: failed to record alert for rule %d",
                    rule["id"], exc_info=True,
                )

        if fired:
            logger.info("AlertEvaluator: %d alert(s) fired this cycle", fired)
