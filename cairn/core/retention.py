"""RetentionManager — policy CRUD, cleanup execution, and dry-run preview.

Manages data retention policies per resource type with optional project scoping.
Legal hold prevents deletion. Audit log enforces minimum 365-day TTL.
Batch deletes (LIMIT 5000) prevent long-running transactions.

Follows the AlertManager pattern (db + config constructor, CRUD + domain logic).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.config import RetentionConfig
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)

# Minimum TTL for audit_log (compliance requirement)
AUDIT_MIN_TTL_DAYS = 365

# Batch size for deletes to avoid long transactions
DELETE_BATCH_SIZE = 5000

# Valid resource types and their cleanup queries
_RESOURCE_CLEANUP: dict[str, dict[str, str]] = {
    "events": {
        "count": """
            SELECT COUNT(*) FROM events
            WHERE created_at < NOW() - make_interval(days => %s)
              AND ({project_filter})
        """,
        "delete": """
            DELETE FROM events WHERE id IN (
                SELECT id FROM events
                WHERE created_at < NOW() - make_interval(days => %s)
                  AND ({project_filter})
                LIMIT %s
            )
        """,
    },
    "usage_events": {
        "count": """
            SELECT COUNT(*) FROM usage_events
            WHERE timestamp < NOW() - make_interval(days => %s)
              AND ({project_filter})
        """,
        "delete": """
            DELETE FROM usage_events WHERE id IN (
                SELECT id FROM usage_events
                WHERE timestamp < NOW() - make_interval(days => %s)
                  AND ({project_filter})
                LIMIT %s
            )
        """,
    },
    "metric_rollups": {
        "count": """
            SELECT COUNT(*) FROM metric_rollups
            WHERE bucket_hour < NOW() - make_interval(days => %s)
              AND ({project_filter})
        """,
        "delete": """
            DELETE FROM metric_rollups WHERE id IN (
                SELECT id FROM metric_rollups
                WHERE bucket_hour < NOW() - make_interval(days => %s)
                  AND ({project_filter})
                LIMIT %s
            )
        """,
    },
    "webhook_deliveries": {
        "count": """
            SELECT COUNT(*) FROM webhook_deliveries
            WHERE created_at < NOW() - make_interval(days => %s)
              AND status IN ('succeeded', 'failed')
        """,
        "delete": """
            DELETE FROM webhook_deliveries WHERE id IN (
                SELECT id FROM webhook_deliveries
                WHERE created_at < NOW() - make_interval(days => %s)
                  AND status IN ('succeeded', 'failed')
                LIMIT %s
            )
        """,
    },
    "alert_history": {
        "count": """
            SELECT COUNT(*) FROM alert_history
            WHERE created_at < NOW() - make_interval(days => %s)
        """,
        "delete": """
            DELETE FROM alert_history WHERE id IN (
                SELECT id FROM alert_history
                WHERE created_at < NOW() - make_interval(days => %s)
                LIMIT %s
            )
        """,
    },
    "audit_log": {
        "count": """
            SELECT COUNT(*) FROM audit_log
            WHERE created_at < NOW() - make_interval(days => %s)
        """,
        "delete": """
            DELETE FROM audit_log WHERE id IN (
                SELECT id FROM audit_log
                WHERE created_at < NOW() - make_interval(days => %s)
                LIMIT %s
            )
        """,
    },
    "event_dispatches": {
        "count": """
            SELECT COUNT(*) FROM event_dispatches
            WHERE completed_at < NOW() - make_interval(days => %s)
              AND status = 'succeeded'
        """,
        "delete": """
            DELETE FROM event_dispatches WHERE id IN (
                SELECT id FROM event_dispatches
                WHERE completed_at < NOW() - make_interval(days => %s)
                  AND status = 'succeeded'
                LIMIT %s
            )
        """,
    },
}

VALID_RESOURCE_TYPES = set(_RESOURCE_CLEANUP.keys())


def _scalar(row) -> int:
    """Extract first column from a row that may be a dict or tuple."""
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


class RetentionManager:
    """Data retention policy management and cleanup execution."""

    def __init__(self, db: Database, config: RetentionConfig):
        self.db = db
        self.config = config

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        resource_type: str,
        ttl_days: int,
        project_id: str | None = None,
        legal_hold: bool = False,
    ) -> dict:
        """Create a retention policy."""
        if resource_type not in VALID_RESOURCE_TYPES:
            raise ValueError(f"Invalid resource_type: {resource_type}. Valid: {sorted(VALID_RESOURCE_TYPES)}")
        if ttl_days < 1:
            raise ValueError("ttl_days must be >= 1")
        # Enforce audit minimum
        effective_ttl = max(ttl_days, AUDIT_MIN_TTL_DAYS) if resource_type == "audit_log" else ttl_days

        row = self.db.execute(
            """
            INSERT INTO retention_policies (project_id, resource_type, ttl_days, legal_hold)
            VALUES (%s, %s, %s, %s)
            RETURNING id, project_id, resource_type, ttl_days, legal_hold, is_active,
                      last_run_at, last_deleted, created_at, updated_at
            """,
            (project_id, resource_type, effective_ttl, legal_hold),
        )
        self.db.commit()
        return self._row_to_dict(row[0])

    def get(self, policy_id: int) -> dict | None:
        """Get a retention policy by ID."""
        rows = self.db.execute(
            """
            SELECT id, project_id, resource_type, ttl_days, legal_hold, is_active,
                   last_run_at, last_deleted, created_at, updated_at
            FROM retention_policies WHERE id = %s
            """,
            (policy_id,),
        )
        self.db.rollback()
        if not rows:
            return None
        return self._row_to_dict(rows[0])

    def list(
        self,
        *,
        resource_type: str | None = None,
        project_id: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List retention policies with optional filtering."""
        conditions = []
        params: list[Any] = []

        if resource_type is not None:
            conditions.append("resource_type = %s")
            params.append(resource_type)
        if project_id is not None:
            conditions.append("project_id = %s")
            params.append(project_id)
        if is_active is not None:
            conditions.append("is_active = %s")
            params.append(is_active)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        count_rows = self.db.execute(
            f"SELECT COUNT(*) FROM retention_policies {where}", params,
        )
        total = _scalar(count_rows[0]) if count_rows else 0

        rows = self.db.execute(
            f"""
            SELECT id, project_id, resource_type, ttl_days, legal_hold, is_active,
                   last_run_at, last_deleted, created_at, updated_at
            FROM retention_policies {where}
            ORDER BY id ASC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        self.db.rollback()
        return {"items": [self._row_to_dict(r) for r in rows], "total": total}

    def update(self, policy_id: int, **updates) -> dict | None:
        """Update a retention policy."""
        allowed = {"resource_type", "ttl_days", "project_id", "legal_hold", "is_active"}
        filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not filtered:
            return self.get(policy_id)

        # Enforce audit minimum
        if "ttl_days" in filtered and filtered.get("resource_type", "") == "audit_log":
            filtered["ttl_days"] = max(filtered["ttl_days"], AUDIT_MIN_TTL_DAYS)

        set_parts = [f"{k} = %s" for k in filtered]
        set_parts.append("updated_at = NOW()")
        params = list(filtered.values()) + [policy_id]

        rows = self.db.execute(
            f"""
            UPDATE retention_policies SET {', '.join(set_parts)}
            WHERE id = %s
            RETURNING id, project_id, resource_type, ttl_days, legal_hold, is_active,
                      last_run_at, last_deleted, created_at, updated_at
            """,
            params,
        )
        self.db.commit()
        if not rows:
            return None
        # Re-check audit TTL for existing audit_log policies being updated
        result = self._row_to_dict(rows[0])
        if result["resource_type"] == "audit_log" and result["ttl_days"] < AUDIT_MIN_TTL_DAYS:
            return self.update(policy_id, ttl_days=AUDIT_MIN_TTL_DAYS)
        return result

    def delete(self, policy_id: int) -> bool:
        """Delete a retention policy."""
        rows = self.db.execute(
            "DELETE FROM retention_policies WHERE id = %s RETURNING id",
            (policy_id,),
        )
        self.db.commit()
        return bool(rows)

    # ------------------------------------------------------------------
    # Cleanup execution
    # ------------------------------------------------------------------

    def preview(self, policy_id: int | None = None) -> list[dict]:
        """Dry-run: show how many rows each policy would delete."""
        if policy_id:
            policy = self.get(policy_id)
            if not policy:
                return []
            policies = [policy]
        else:
            result = self.list(is_active=True, limit=100)
            policies = result["items"]

        previews = []
        for p in policies:
            if p["legal_hold"]:
                previews.append({**p, "would_delete": 0, "reason": "legal_hold"})
                continue

            ttl = max(p["ttl_days"], AUDIT_MIN_TTL_DAYS) if p["resource_type"] == "audit_log" else p["ttl_days"]
            templates = _RESOURCE_CLEANUP.get(p["resource_type"])
            if not templates:
                continue

            query = templates["count"]
            params = self._build_params(query, ttl, p.get("project_id"))
            query = self._apply_project_filter(query, p.get("project_id"))

            try:
                rows = self.db.execute(query, params)
                self.db.rollback()
                count = _scalar(rows[0]) if rows else 0
            except Exception:
                logger.warning("Preview failed for policy %d", p["id"], exc_info=True)
                count = -1

            previews.append({**p, "would_delete": count})
        return previews

    def run_cleanup(self, *, dry_run: bool = True) -> list[dict]:
        """Execute all active retention policies.

        Returns list of results per policy with deleted count.
        """
        result = self.list(is_active=True, limit=100)
        policies = result["items"]
        results = []

        for p in policies:
            if p["legal_hold"]:
                results.append({"policy_id": p["id"], "resource_type": p["resource_type"],
                                "deleted": 0, "reason": "legal_hold"})
                continue

            ttl = max(p["ttl_days"], AUDIT_MIN_TTL_DAYS) if p["resource_type"] == "audit_log" else p["ttl_days"]
            templates = _RESOURCE_CLEANUP.get(p["resource_type"])
            if not templates:
                continue

            if dry_run:
                # Count only
                query = templates["count"]
                params = self._build_params(query, ttl, p.get("project_id"))
                query = self._apply_project_filter(query, p.get("project_id"))
                try:
                    rows = self.db.execute(query, params)
                    self.db.rollback()
                    count = _scalar(rows[0]) if rows else 0
                except Exception:
                    logger.warning("Dry-run count failed for policy %d", p["id"], exc_info=True)
                    count = -1
                results.append({"policy_id": p["id"], "resource_type": p["resource_type"],
                                "would_delete": count, "dry_run": True})
            else:
                # Batch delete
                total_deleted = 0
                delete_query = templates["delete"]
                params = self._build_params(delete_query, ttl, p.get("project_id"), batch=True)
                delete_query = self._apply_project_filter(delete_query, p.get("project_id"))

                try:
                    while True:
                        rows = self.db.execute(delete_query, params)
                        self.db.commit()
                        # rowcount from DELETE
                        batch_deleted = len(rows) if rows else 0
                        if batch_deleted == 0:
                            break
                        total_deleted += batch_deleted
                except Exception:
                    logger.warning("Cleanup failed for policy %d after %d deletes",
                                   p["id"], total_deleted, exc_info=True)

                # Update policy stats
                try:
                    self.db.execute(
                        """
                        UPDATE retention_policies
                        SET last_run_at = NOW(), last_deleted = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (total_deleted, p["id"]),
                    )
                    self.db.commit()
                except Exception:
                    logger.warning("Failed to update policy stats for %d", p["id"], exc_info=True)

                results.append({"policy_id": p["id"], "resource_type": p["resource_type"],
                                "deleted": total_deleted, "dry_run": False})

        return results

    def status(self) -> dict:
        """Return retention scan status."""
        rows = self.db.execute(
            """
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE is_active) as active,
                   COUNT(*) FILTER (WHERE legal_hold) as held,
                   MIN(last_run_at) as oldest_run,
                   MAX(last_run_at) as latest_run,
                   SUM(last_deleted) as total_deleted
            FROM retention_policies
            """,
        )
        self.db.rollback()
        r = rows[0] if rows else {"total": 0, "active": 0, "held": 0, "oldest_run": None, "latest_run": None, "total_deleted": 0}
        # Support both dict rows (psycopg3) and tuple rows (tests)
        if isinstance(r, dict):
            total, active, held = r["total"], r["active"], r["held"]
            oldest, latest, deleted = r["oldest_run"], r["latest_run"], r["total_deleted"]
        else:
            total, active, held = r[0], r[1], r[2]
            oldest, latest, deleted = r[3], r[4], r[5]
        return {
            "total_policies": total,
            "active_policies": active,
            "held_policies": held,
            "last_run_at": latest.isoformat() if latest else None,
            "earliest_policy": oldest.isoformat() if oldest else None,
            "total_deleted": deleted or 0,
            "scan_interval_hours": self.config.scan_interval_hours,
            "dry_run": self.config.dry_run,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_params(self, query: str, ttl: int, project_id: str | None, batch: bool = False) -> list:
        """Build query params based on whether project filter is present."""
        params: list[Any] = [ttl]
        if "{project_filter}" in query and project_id is not None:
            params.append(project_id)
        if batch:
            params.append(DELETE_BATCH_SIZE)
        return params

    def _apply_project_filter(self, query: str, project_id: str | None) -> str:
        """Replace project filter placeholder."""
        if "{project_filter}" not in query:
            return query
        if project_id is not None:
            return query.replace("{project_filter}", "project_id = %s")
        return query.replace("{project_filter}", "true")

    @staticmethod
    def _row_to_dict(row) -> dict:
        # Support both dict rows (psycopg3) and tuple rows (tests)
        if isinstance(row, dict):
            la = row.get("last_run_at")
            ca = row.get("created_at")
            ua = row.get("updated_at")
            return {
                "id": row["id"],
                "project_id": row.get("project_id"),
                "resource_type": row["resource_type"],
                "ttl_days": row["ttl_days"],
                "legal_hold": row["legal_hold"],
                "is_active": row["is_active"],
                "last_run_at": la.isoformat() if la else None,
                "last_deleted": row.get("last_deleted", 0),
                "created_at": ca.isoformat() if ca else None,
                "updated_at": ua.isoformat() if ua else None,
            }
        return {
            "id": row[0],
            "project_id": row[1],
            "resource_type": row[2],
            "ttl_days": row[3],
            "legal_hold": row[4],
            "is_active": row[5],
            "last_run_at": row[6].isoformat() if row[6] else None,
            "last_deleted": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None,
        }
