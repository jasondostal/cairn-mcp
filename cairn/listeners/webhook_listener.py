"""WebhookListener — creates delivery records for matching webhook subscriptions.

Subscribes to * (all events). For each event, queries active webhooks
with matching event_type patterns and creates webhook_delivery records
for the WebhookDeliveryWorker to process.

Never makes HTTP calls itself — that is the delivery worker's job.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.core.webhooks import WebhookManager

logger = logging.getLogger(__name__)


class WebhookListener:
    """Creates webhook delivery records for matching events."""

    def __init__(self, webhook_manager: WebhookManager):
        self.webhooks = webhook_manager

    def register(self, event_bus: EventBus) -> None:
        """Subscribe to all events."""
        event_bus.subscribe("*", "webhook_dispatch", self.handle)

    def handle(self, event: dict) -> None:
        """Find matching webhooks and create delivery records."""
        event_type = event.get("event_type", "")
        if not event_type:
            return

        event_id = event.get("event_id")
        if not event_id:
            return

        project_id = event.get("project_id")

        try:
            matching = self.webhooks.find_matching_webhooks(event_type, project_id)
        except Exception:
            logger.warning(
                "WebhookListener: failed to find matching webhooks for %s",
                event_type, exc_info=True,
            )
            return

        for webhook in matching:
            try:
                payload = self.webhooks.build_payload(event, webhook)
                self.webhooks.create_delivery(
                    webhook_id=webhook["id"],
                    event_id=event_id,
                    request_body=payload,
                )
            except Exception:
                logger.warning(
                    "WebhookListener: failed to create delivery for webhook %d event %d",
                    webhook["id"], event_id, exc_info=True,
                )

        if matching:
            logger.debug(
                "WebhookListener: %d deliveries created for %s event %d",
                len(matching), event_type, event_id,
            )
