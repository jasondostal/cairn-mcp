"""NotificationListener — fans out events to in-app notifications.

Subscribes to all events (*). For each event, queries active subscriptions
with matching patterns and creates in-app notification records.

Lightweight: only does DB lookups + inserts, no HTTP calls.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.core.subscriptions import SubscriptionManager

logger = logging.getLogger(__name__)


class NotificationListener:
    """Creates in-app notifications for matching event subscriptions."""

    def __init__(self, subscription_manager: SubscriptionManager):
        self.subscriptions = subscription_manager

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe("*", "notification_dispatch", self.handle)

    def handle(self, event: dict) -> None:
        event_type = event.get("event_type", "")
        if not event_type:
            return

        # Skip internal/noisy events
        if event_type.startswith("session_"):
            return

        try:
            created = self.subscriptions.notify_for_event(event)
            if created:
                logger.debug(
                    "NotificationListener: %d notifications for %s event %s",
                    created, event_type, event.get("event_id"),
                )
        except Exception:
            logger.warning(
                "NotificationListener: failed to process %s event %s",
                event_type, event.get("event_id"), exc_info=True,
            )
