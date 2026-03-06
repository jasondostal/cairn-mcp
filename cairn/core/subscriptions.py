"""SubscriptionManager — CRUD for event subscriptions and notification dispatch.

Part of ca-146: pattern-based subscribe/notify for human/agent collaboration.
"""

from __future__ import annotations

import builtins
import fnmatch
import logging
from typing import TYPE_CHECKING

from cairn.core.utils import get_or_create_project

if TYPE_CHECKING:
    from cairn.listeners.push_notifier import PushNotifier
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)

# Default notification title templates by event type prefix
_TITLE_TEMPLATES: dict[str, str] = {
    "work_item.completed": "Work item completed",
    "work_item.gated": "Work item needs input",
    "deliverable.created": "Deliverable ready for review",
    "deliverable.approved": "Deliverable approved",
    "deliverable.revised": "Deliverable needs revision",
    "deliverable.rejected": "Deliverable rejected",
    "memory.created": "New memory stored",
}

_SEVERITY_MAP: dict[str, str] = {
    "work_item.completed": "success",
    "work_item.gated": "warning",
    "deliverable.created": "info",
    "deliverable.approved": "success",
    "deliverable.revised": "warning",
    "deliverable.rejected": "error",
}


class SubscriptionManager:
    """Manages event subscriptions and creates in-app notifications."""

    def __init__(self, db: Database, push_notifier: PushNotifier | None = None):
        self.db = db
        self.push_notifier = push_notifier

    # ------------------------------------------------------------------
    # Subscription CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        patterns: list[str],
        channel: str = "in_app",
        channel_config: dict | None = None,
        project: str | None = None,
    ) -> dict:
        """Create an event subscription."""
        project_id = get_or_create_project(self.db, project) if project else None

        row = self.db.execute_one(
            """
            INSERT INTO event_subscriptions (name, patterns, channel, channel_config, project_id)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            RETURNING id, name, patterns, channel, channel_config, project_id, is_active, created_at
            """,
            (name, patterns, channel,
             __import__("json").dumps(channel_config or {}),
             project_id),
        )
        self.db.commit()
        assert row is not None
        return self._sub_to_dict(row)

    def list(
        self,
        channel: str | None = None,
        project: str | None = None,
        active_only: bool = True,
    ) -> builtins.list[dict]:
        """List subscriptions with optional filters."""
        where = []
        params: list = []
        if active_only:
            where.append("s.is_active = true")
        if channel:
            where.append("s.channel = %s")
            params.append(channel)
        if project:
            where.append("(p.name = %s OR s.project_id IS NULL)")
            params.append(project)

        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = self.db.execute(
            f"""
            SELECT s.*, p.name AS project_name
            FROM event_subscriptions s
            LEFT JOIN projects p ON s.project_id = p.id
            {where_clause}
            ORDER BY s.created_at DESC
            """,
            tuple(params),
        )
        return [self._sub_to_dict(r) for r in rows]

    def get(self, subscription_id: int) -> dict | None:
        row = self.db.execute_one(
            """
            SELECT s.*, p.name AS project_name
            FROM event_subscriptions s
            LEFT JOIN projects p ON s.project_id = p.id
            WHERE s.id = %s
            """,
            (subscription_id,),
        )
        return self._sub_to_dict(row) if row else None

    def update(self, subscription_id: int, **fields) -> dict:
        """Update a subscription."""
        allowed = {"name", "patterns", "channel", "channel_config", "is_active"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get(subscription_id) or {}

        set_parts = []
        params: list = []
        for k, v in updates.items():
            if k == "channel_config":
                set_parts.append(f"{k} = %s::jsonb")
                params.append(__import__("json").dumps(v))
            else:
                set_parts.append(f"{k} = %s")
                params.append(v)
        set_parts.append("updated_at = NOW()")
        params.append(subscription_id)

        self.db.execute(
            f"UPDATE event_subscriptions SET {', '.join(set_parts)} WHERE id = %s",
            tuple(params),
        )
        self.db.commit()
        return self.get(subscription_id) or {}

    def delete(self, subscription_id: int) -> dict:
        self.db.execute(
            "UPDATE event_subscriptions SET is_active = false WHERE id = %s",
            (subscription_id,),
        )
        self.db.commit()
        return {"id": subscription_id, "action": "deactivated"}

    # ------------------------------------------------------------------
    # Pattern matching
    # ------------------------------------------------------------------

    def find_matching(self, event_type: str, project_id: int | None = None) -> builtins.list[dict]:
        """Find active subscriptions whose patterns match an event type.

        Pattern syntax:
        - Exact: "work_item.completed"
        - Wildcard: "work_item.*" or "*"
        - Filtered: "work_item.gated:project=cairn" (future)
        """
        rows = self.db.execute(
            """
            SELECT s.*, p.name AS project_name
            FROM event_subscriptions s
            LEFT JOIN projects p ON s.project_id = p.id
            WHERE s.is_active = true
              AND (s.project_id IS NULL OR s.project_id = %s)
            """,
            (project_id,),
        )

        matched = []
        for row in rows:
            patterns = row.get("patterns") or []
            for pattern in patterns:
                # Strip filter suffix for matching (e.g., "work_item.gated:project=cairn")
                match_pattern = pattern.split(":")[0] if ":" in pattern else pattern
                if fnmatch.fnmatch(event_type, match_pattern):
                    matched.append(self._sub_to_dict(row))
                    break  # One match per subscription is enough

        return matched

    # ------------------------------------------------------------------
    # Notification dispatch
    # ------------------------------------------------------------------

    def create_notification(
        self,
        subscription_id: int | None,
        event_id: int | None,
        title: str,
        body: str | None = None,
        severity: str = "info",
        metadata: dict | None = None,
    ) -> dict:
        """Create an in-app notification."""
        import json

        row = self.db.execute_one(
            """
            INSERT INTO notifications (subscription_id, event_id, title, body, severity, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id, title, severity, is_read, created_at
            """,
            (subscription_id, event_id, title, body, severity,
             json.dumps(metadata or {})),
        )
        self.db.commit()
        assert row is not None
        return self._notif_to_dict(row)

    def list_notifications(
        self,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List notifications, newest first."""
        where = "WHERE is_read = false" if unread_only else ""
        rows = self.db.execute(
            f"""
            SELECT * FROM notifications
            {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        count_row = self.db.execute_one(
            f"SELECT COUNT(*) AS total FROM notifications {where}",
        )
        unread_row = self.db.execute_one(
            "SELECT COUNT(*) AS total FROM notifications WHERE is_read = false",
        )
        assert count_row is not None
        assert unread_row is not None
        return {
            "items": [self._notif_to_dict(r) for r in rows],
            "total": count_row["total"],
            "unread": unread_row["total"],
            "limit": limit,
            "offset": offset,
        }

    def mark_read(self, notification_id: int) -> dict:
        """Mark a single notification as read."""
        self.db.execute(
            "UPDATE notifications SET is_read = true, read_at = NOW() WHERE id = %s",
            (notification_id,),
        )
        self.db.commit()
        return {"id": notification_id, "is_read": True}

    def mark_all_read(self) -> dict:
        """Mark all unread notifications as read."""
        result = self.db.execute(
            "UPDATE notifications SET is_read = true, read_at = NOW() WHERE is_read = false RETURNING id",
        )
        self.db.commit()
        return {"marked": len(result)}

    def unread_count(self) -> int:
        """Get count of unread notifications."""
        row = self.db.execute_one(
            "SELECT COUNT(*) AS total FROM notifications WHERE is_read = false",
        )
        assert row is not None
        return row["total"]

    # ------------------------------------------------------------------
    # Notification generation from events
    # ------------------------------------------------------------------

    def notify_for_event(self, event: dict) -> int:
        """Process an event: find matching subscriptions, create notifications.

        Returns the number of notifications created.
        """
        event_type = event.get("event_type", "")
        event_id = event.get("event_id")
        project_id = event.get("project_id")
        payload = event.get("payload") or {}

        subscriptions = self.find_matching(event_type, project_id)
        created = 0

        for sub in subscriptions:
            channel = sub.get("channel", "in_app")
            title = self._build_title(event_type, payload)
            body = self._build_body(event_type, payload)
            severity = _SEVERITY_MAP.get(event_type, "info")

            if channel == "in_app":
                self.create_notification(
                    subscription_id=sub["id"],
                    event_id=event_id,
                    title=title,
                    body=body,
                    severity=severity,
                    metadata={
                        "event_type": event_type,
                        "work_item_id": event.get("work_item_id"),
                        **{k: v for k, v in payload.items()
                           if isinstance(v, (str, int, float, bool)) and k != "content"},
                    },
                )
                created += 1

            elif channel == "push" and self.push_notifier and self.push_notifier.enabled:
                channel_config = sub.get("channel_config") or {}
                topic = channel_config.get("topic")
                sent = self.push_notifier.send(
                    title=title,
                    body=body,
                    severity=severity,
                    topic=topic,
                )
                if sent:
                    created += 1

        return created

    def _build_title(self, event_type: str, payload: dict) -> str:
        """Build a human-readable notification title."""
        base = _TITLE_TEMPLATES.get(event_type, event_type.replace(".", " ").replace("_", " ").title())
        # Add context from payload
        if payload.get("title"):
            return f"{base}: {payload['title']}"
        if payload.get("work_item_id"):
            return f"{base} (#{payload['work_item_id']})"
        return base

    def _build_body(self, event_type: str, payload: dict) -> str | None:
        """Build notification body from payload."""
        parts = []
        if payload.get("summary"):
            parts.append(payload["summary"])
        if payload.get("description"):
            parts.append(payload["description"][:200])
        if payload.get("reviewer"):
            parts.append(f"Reviewer: {payload['reviewer']}")
        if payload.get("assignee"):
            parts.append(f"Assignee: {payload['assignee']}")
        return "\n".join(parts) if parts else None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sub_to_dict(self, row: dict) -> dict:
        d = dict(row)
        for ts in ("created_at", "updated_at"):
            if d.get(ts) and hasattr(d[ts], "isoformat"):
                d[ts] = d[ts].isoformat()
        return d

    def _notif_to_dict(self, row: dict) -> dict:
        d = dict(row)
        for ts in ("created_at", "read_at"):
            if d.get(ts) and hasattr(d[ts], "isoformat"):
                d[ts] = d[ts].isoformat()
        return d
