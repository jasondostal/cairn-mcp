"""WebhookDeliveryWorker — background thread that delivers webhook HTTP calls.

Polls the webhook_deliveries table for pending/failed records, makes HTTP POST
requests to webhook URLs with HMAC-SHA256 signing, and tracks success/failure
with exponential backoff retry.

Follows the same thread lifecycle pattern as EventDispatcher and DecayWorker.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from cairn.core.webhooks import sign_payload

if TYPE_CHECKING:
    from cairn.config import WebhookConfig
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class WebhookDeliveryWorker:
    """Background thread that delivers webhooks via HTTP POST."""

    def __init__(self, db: Database, config: WebhookConfig):
        self.db = db
        self.config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the delivery loop in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="WebhookDeliveryWorker",
        )
        self._thread.start()
        logger.info("WebhookDeliveryWorker: started (interval=%.1fs)", self.config.delivery_interval)

    def stop(self) -> None:
        """Signal stop and wait for the thread to finish."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.warning("WebhookDeliveryWorker: thread did not stop within timeout")
        else:
            logger.info("WebhookDeliveryWorker: stopped")
        self._thread = None

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception:
                logger.warning("WebhookDeliveryWorker: poll cycle failed", exc_info=True)
            self._stop_event.wait(timeout=self.config.delivery_interval)
        # Final drain on shutdown
        try:
            self._poll()
        except Exception:
            pass

    def _poll(self) -> None:
        """Fetch pending deliveries and make HTTP calls."""
        rows = self.db.execute(
            """
            SELECT wd.id, wd.webhook_id, wd.event_id, wd.attempts,
                   wd.max_attempts, wd.request_body,
                   w.url, w.secret
            FROM webhook_deliveries wd
            JOIN webhooks w ON w.id = wd.webhook_id
            WHERE wd.status IN ('pending', 'failed')
              AND wd.next_retry <= NOW()
              AND wd.attempts < wd.max_attempts
              AND w.is_active = true
            ORDER BY wd.id ASC
            LIMIT %s
            """,
            (self.config.delivery_batch_size,),
        )

        if not rows:
            self.db.rollback()
            return

        processed = 0
        for row in rows:
            self._deliver(row)
            processed += 1

        if processed:
            logger.info("WebhookDeliveryWorker: processed %d deliveries", processed)

    # ------------------------------------------------------------------
    # HTTP delivery
    # ------------------------------------------------------------------

    def _deliver(self, row: dict) -> None:
        """Make HTTP POST to webhook URL."""
        delivery_id = row["id"]
        url = row["url"]
        secret = row["secret"]
        request_body = row["request_body"] or {}

        payload_bytes = json.dumps(request_body, separators=(",", ":")).encode("utf-8")
        signature = sign_payload(payload_bytes, secret)

        req = urllib.request.Request(
            url,
            data=payload_bytes,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Cairn-Webhook/1.0",
                "X-Cairn-Signature": f"sha256={signature}",
                "X-Cairn-Event": request_body.get("event_type", ""),
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                status_code = resp.status
                body = resp.read().decode("utf-8", errors="replace")[:2000]

            if 200 <= status_code < 300:
                self._mark_success(delivery_id, status_code, body)
            else:
                self._mark_failed(
                    delivery_id, row["attempts"],
                    f"HTTP {status_code}: {body[:500]}",
                    status_code,
                )
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:2000]
            except Exception:
                pass
            self._mark_failed(
                delivery_id, row["attempts"],
                f"HTTP {exc.code}: {body[:500]}",
                exc.code,
            )
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            self._mark_failed(
                delivery_id, row["attempts"],
                f"Connection error: {exc}",
            )

    # ------------------------------------------------------------------
    # Status updates
    # ------------------------------------------------------------------

    def _mark_success(self, delivery_id: int, status_code: int, body: str) -> None:
        self.db.execute(
            """
            UPDATE webhook_deliveries
            SET status = 'success', response_status = %s, response_body = %s,
                attempts = attempts + 1, completed_at = NOW()
            WHERE id = %s
            """,
            (status_code, body, delivery_id),
        )
        self.db.commit()

    def _mark_failed(
        self,
        delivery_id: int,
        current_attempts: int,
        error: str,
        status_code: int | None = None,
    ) -> None:
        next_attempts = current_attempts + 1
        backoff_seconds = self.config.backoff_base * (2 ** current_attempts)

        # Check if this was the last attempt
        row = self.db.execute_one(
            "SELECT max_attempts FROM webhook_deliveries WHERE id = %s",
            (delivery_id,),
        )
        max_attempts = row["max_attempts"] if row else self.config.max_attempts

        if next_attempts >= max_attempts:
            self._mark_exhausted(delivery_id, next_attempts, error, status_code)
            return

        self.db.execute(
            """
            UPDATE webhook_deliveries
            SET status = 'failed',
                attempts = %s,
                last_error = %s,
                response_status = %s,
                next_retry = NOW() + make_interval(secs => %s)
            WHERE id = %s
            """,
            (next_attempts, error[:2000], status_code, backoff_seconds, delivery_id),
        )
        self.db.commit()
        logger.debug(
            "WebhookDeliveryWorker: delivery %d failed (attempt %d), retry in %ds",
            delivery_id, next_attempts, backoff_seconds,
        )

    def _mark_exhausted(
        self,
        delivery_id: int,
        attempts: int,
        error: str,
        status_code: int | None = None,
    ) -> None:
        self.db.execute(
            """
            UPDATE webhook_deliveries
            SET status = 'exhausted', attempts = %s, last_error = %s,
                response_status = %s, completed_at = NOW()
            WHERE id = %s
            """,
            (attempts, error[:2000], status_code, delivery_id),
        )
        self.db.commit()
        logger.warning(
            "WebhookDeliveryWorker: delivery %d exhausted after %d attempts",
            delivery_id, attempts,
        )
