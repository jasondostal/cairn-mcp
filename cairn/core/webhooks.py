"""WebhookManager — CRUD, matching, and delivery for webhook subscriptions.

Manages webhook subscriptions per project. Provides matching logic to
determine which webhooks should fire for a given event, and creates
delivery records for the WebhookDeliveryWorker to process.
"""

from __future__ import annotations

import builtins
import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cairn.config import WebhookConfig
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


def generate_secret() -> str:
    """Generate a 32-byte hex secret for HMAC signing."""
    return os.urandom(32).hex()


def sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for a payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def _matches_pattern(event_type: str, pattern: str) -> bool:
    """Check if an event_type matches a subscription pattern.

    Supports:
    - Exact: 'memory.created' matches 'memory.created'
    - Domain wildcard: 'work_item.*' matches 'work_item.completed'
    - Global wildcard: '*' matches everything
    """
    if pattern == "*":
        return True
    if pattern == event_type:
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return event_type.startswith(prefix + ".")
    return False


class WebhookManager:
    """CRUD + matching + delivery creation for webhooks."""

    def __init__(self, db: Database, config: WebhookConfig):
        self.db = db
        self.config = config

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        url: str,
        event_types: list[str],
        project_id: int | None = None,
        secret: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create a webhook subscription. Returns the created webhook."""
        if not secret:
            secret = generate_secret()

        row = self.db.execute_one(
            """
            INSERT INTO webhooks
                (project_id, name, url, secret, event_types, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id, project_id, name, url, secret, event_types,
                      is_active, metadata, created_at, updated_at
            """,
            (
                project_id, name, url, secret,
                event_types,
                json.dumps(metadata or {}),
            ),
        )
        assert row is not None
        self.db.commit()
        logger.info("Webhook created: id=%d name='%s' url=%s", row["id"], name, url)
        return self._row_to_dict(row)

    def get(self, webhook_id: int) -> dict | None:
        """Get a single webhook by ID."""
        row = self.db.execute_one(
            """
            SELECT id, project_id, name, url, secret, event_types,
                   is_active, metadata, created_at, updated_at
            FROM webhooks WHERE id = %s
            """,
            (webhook_id,),
        )
        return self._row_to_dict(row) if row else None

    def list(
        self,
        *,
        project_id: int | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List webhooks with optional project filter."""
        where: list[str] = []
        params: list[Any] = []

        if project_id is not None:
            where.append("w.project_id = %s")
            params.append(project_id)
        if active_only:
            where.append("w.is_active = true")

        where_clause = " AND ".join(where) if where else "TRUE"

        count_row = self.db.execute_one(
            f"SELECT COUNT(*) as total FROM webhooks w WHERE {where_clause}",
            tuple(params),
        )
        total = count_row["total"] if count_row else 0

        query_params = list(params)
        query_params.extend([limit, offset])

        rows = self.db.execute(
            f"""
            SELECT w.id, w.project_id, w.name, w.url, w.secret, w.event_types,
                   w.is_active, w.metadata, w.created_at, w.updated_at,
                   p.name as project
            FROM webhooks w
            LEFT JOIN projects p ON w.project_id = p.id
            WHERE {where_clause}
            ORDER BY w.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(query_params),
        )

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [self._row_to_dict(r) for r in rows],
        }

    def update(self, webhook_id: int, **updates) -> dict | None:
        """Update webhook fields. Returns updated webhook or None."""
        allowed = {"name", "url", "event_types", "is_active", "metadata"}
        filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not filtered:
            return self.get(webhook_id)

        set_parts = []
        params: list[Any] = []
        for key, value in filtered.items():
            if key == "metadata":
                set_parts.append(f"{key} = %s::jsonb")
                params.append(json.dumps(value))
            else:
                set_parts.append(f"{key} = %s")
                params.append(value)

        set_parts.append("updated_at = NOW()")
        params.append(webhook_id)

        row = self.db.execute_one(
            f"""
            UPDATE webhooks
            SET {', '.join(set_parts)}
            WHERE id = %s
            RETURNING id, project_id, name, url, secret, event_types,
                      is_active, metadata, created_at, updated_at
            """,
            tuple(params),
        )
        self.db.commit()
        return self._row_to_dict(row) if row else None

    def delete(self, webhook_id: int) -> bool:
        """Delete a webhook and all its deliveries (CASCADE)."""
        row = self.db.execute_one(
            "DELETE FROM webhooks WHERE id = %s RETURNING id",
            (webhook_id,),
        )
        self.db.commit()
        if row:
            logger.info("Webhook deleted: id=%d", webhook_id)
        return row is not None

    def rotate_secret(self, webhook_id: int) -> dict | None:
        """Generate a new signing secret."""
        new_secret = generate_secret()
        row = self.db.execute_one(
            """
            UPDATE webhooks
            SET secret = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, project_id, name, url, secret, event_types,
                      is_active, metadata, created_at, updated_at
            """,
            (new_secret, webhook_id),
        )
        self.db.commit()
        return self._row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def find_matching_webhooks(self, event_type: str, project_id: int | None) -> builtins.list[dict]:
        """Find all active webhooks that match an event type.

        Checks webhooks scoped to the event's project AND global webhooks
        (project_id IS NULL).
        """
        where_parts = ["is_active = true"]
        params: list[Any] = []

        if project_id is not None:
            where_parts.append("(project_id = %s OR project_id IS NULL)")
            params.append(project_id)
        else:
            where_parts.append("project_id IS NULL")

        rows = self.db.execute(
            f"""
            SELECT id, project_id, name, url, secret, event_types,
                   is_active, metadata, created_at, updated_at
            FROM webhooks
            WHERE {' AND '.join(where_parts)}
            """,
            tuple(params),
        )

        matched = []
        for row in rows:
            event_patterns = row["event_types"] or []
            for pattern in event_patterns:
                if _matches_pattern(event_type, pattern):
                    matched.append(self._row_to_dict(row))
                    break
        return matched

    # ------------------------------------------------------------------
    # Delivery creation
    # ------------------------------------------------------------------

    def create_delivery(
        self,
        *,
        webhook_id: int,
        event_id: int,
        request_body: dict,
    ) -> int:
        """Create a pending delivery record. Returns delivery ID."""
        row = self.db.execute_one(
            """
            INSERT INTO webhook_deliveries
                (webhook_id, event_id, request_body, max_attempts)
            VALUES (%s, %s, %s::jsonb, %s)
            RETURNING id
            """,
            (webhook_id, event_id, json.dumps(request_body), self.config.max_attempts),
        )
        assert row is not None
        self.db.commit()
        return row["id"]

    def build_payload(self, event: dict, webhook: dict) -> dict:
        """Build the standard webhook payload from an event dict."""
        return {
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "trace_id": event.get("trace_id"),
            "project_id": event.get("project_id"),
            "work_item_id": event.get("work_item_id"),
            "session_name": event.get("session_name"),
            "payload": event.get("payload", {}),
            "webhook_id": webhook["id"],
            "webhook_name": webhook["name"],
            "delivered_at": datetime.now(UTC).isoformat(),
        }

    # ------------------------------------------------------------------
    # Delivery queries
    # ------------------------------------------------------------------

    def list_deliveries(
        self,
        *,
        webhook_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Query webhook deliveries with filters."""
        where: list[str] = []
        params: list[Any] = []

        if webhook_id is not None:
            where.append("wd.webhook_id = %s")
            params.append(webhook_id)
        if status:
            where.append("wd.status = %s")
            params.append(status)

        where_clause = " AND ".join(where) if where else "TRUE"

        count_row = self.db.execute_one(
            f"SELECT COUNT(*) as total FROM webhook_deliveries wd WHERE {where_clause}",
            tuple(params),
        )
        total = count_row["total"] if count_row else 0

        query_params = list(params)
        query_params.extend([limit, offset])

        rows = self.db.execute(
            f"""
            SELECT wd.id, wd.webhook_id, wd.event_id, wd.status,
                   wd.attempts, wd.max_attempts,
                   wd.response_status, wd.response_body, wd.last_error,
                   wd.created_at, wd.completed_at,
                   w.name as webhook_name, w.url as webhook_url
            FROM webhook_deliveries wd
            JOIN webhooks w ON w.id = wd.webhook_id
            WHERE {where_clause}
            ORDER BY wd.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(query_params),
        )

        items = [
            {
                "id": r["id"],
                "webhook_id": r["webhook_id"],
                "webhook_name": r["webhook_name"],
                "webhook_url": r["webhook_url"],
                "event_id": r["event_id"],
                "status": r["status"],
                "attempts": r["attempts"],
                "max_attempts": r["max_attempts"],
                "response_status": r["response_status"],
                "response_body": r["response_body"],
                "last_error": r["last_error"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            }
            for r in rows
        ]

        return {"total": total, "limit": limit, "offset": offset, "items": items}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "url": row["url"],
            "secret": row["secret"],
            "event_types": list(row["event_types"] or []),
            "is_active": row["is_active"],
            "metadata": row["metadata"] or {},
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
