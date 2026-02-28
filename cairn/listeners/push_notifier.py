"""PushNotifier — sends push notifications via ntfy.sh.

Handles the 'push' channel for event subscriptions. When an event matches
a push-channel subscription, sends an HTTP POST to the configured ntfy server.

ntfy.sh protocol: POST to https://ntfy.sh/<topic> with title/body/priority headers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import httpx

if TYPE_CHECKING:
    from cairn.config import PushConfig

logger = logging.getLogger(__name__)

# Map cairn severity → ntfy priority (1=min, 3=default, 5=max)
_PRIORITY_MAP: dict[str, int] = {
    "info": 3,       # default
    "success": 3,    # default
    "warning": 4,    # high
    "error": 5,      # max (urgent)
}

# Map cairn severity → ntfy tags (emoji shortcodes)
_TAG_MAP: dict[str, str] = {
    "info": "information_source",
    "success": "white_check_mark",
    "warning": "warning",
    "error": "rotating_light",
}


class PushNotifier:
    """Sends push notifications to ntfy.sh or compatible services."""

    def __init__(self, config: PushConfig):
        self.config = config
        self._client: httpx.Client | None = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled and bool(self.config.url)

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            headers = {}
            if self.config.token:
                headers["Authorization"] = f"Bearer {self.config.token}"
            self._client = httpx.Client(
                timeout=self.config.timeout,
                headers=headers,
            )
        return self._client

    def send(
        self,
        title: str,
        body: str | None = None,
        severity: str = "info",
        topic: str | None = None,
        click_url: str | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Send a push notification.

        Returns True if sent successfully, False otherwise.
        """
        if not self.enabled:
            return False

        target_topic = topic or self.config.default_topic
        url = urljoin(self.config.url.rstrip("/") + "/", target_topic)

        # Build ntfy headers
        headers: dict[str, str] = {
            "Title": title[:256],  # ntfy max title length
            "Priority": str(_PRIORITY_MAP.get(severity, 3)),
        }

        # Add tags
        ntfy_tags = list(tags or [])
        if severity in _TAG_MAP:
            ntfy_tags.insert(0, _TAG_MAP[severity])
        if ntfy_tags:
            headers["Tags"] = ",".join(ntfy_tags)

        # Click action — open cairn UI when notification is tapped
        if click_url:
            headers["Click"] = click_url

        message = body or title

        try:
            client = self._get_client()
            resp = client.post(url, content=message, headers=headers)
            resp.raise_for_status()
            logger.debug("Push notification sent: %s → %s", title, target_topic)
            return True
        except Exception:
            logger.warning(
                "Failed to send push notification: %s → %s",
                title, target_topic, exc_info=True,
            )
            return False

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
