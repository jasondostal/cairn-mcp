"""AuditManager — append-only compliance log for all mutations.

Immutable by design: log() and query() only. No update or delete methods.
Every mutation event gets a tamper-evident entry with trace correlation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class AuditManager:
    """Append-only audit log. No update/delete — immutability enforced in code."""

    def __init__(self, db: Database):
        self.db = db

    def log(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: int | None = None,
        project_id: int | None = None,
        session_name: str | None = None,
        trace_id: str | None = None,
        actor: str | None = None,
        entry_point: str | None = None,
        before_state: dict | None = None,
        after_state: dict | None = None,
        metadata: dict | None = None,
    ) -> int:
        """Write an immutable audit entry. Returns the audit log ID."""
        row = self.db.execute_one(
            """
            INSERT INTO audit_log
                (trace_id, actor, entry_point, action, resource_type,
                 resource_id, project_id, session_name,
                 before_state, after_state, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
            RETURNING id
            """,
            (
                trace_id, actor, entry_point, action, resource_type,
                resource_id, project_id, session_name,
                json.dumps(before_state) if before_state else None,
                json.dumps(after_state) if after_state else None,
                json.dumps(metadata or {}),
            ),
        )
        self.db.commit()
        audit_id = row["id"]
        logger.debug(
            "Audit: %s %s/%s trace=%s",
            action, resource_type, resource_id, trace_id,
        )
        return audit_id

    def query(
        self,
        *,
        trace_id: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        project: str | None = None,
        days: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Query audit log with filters. Returns {total, items, limit, offset}."""
        where: list[str] = []
        params: list[Any] = []

        if trace_id:
            where.append("a.trace_id = %s")
            params.append(trace_id)
        if actor:
            where.append("a.actor = %s")
            params.append(actor)
        if action:
            where.append("a.action = %s")
            params.append(action)
        if resource_type:
            where.append("a.resource_type = %s")
            params.append(resource_type)
        if resource_id is not None:
            where.append("a.resource_id = %s")
            params.append(resource_id)
        if project:
            where.append("a.project_id = (SELECT id FROM projects WHERE name = %s)")
            params.append(project)
        if days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            where.append("a.created_at >= %s")
            params.append(cutoff)

        where_clause = " AND ".join(where) if where else "TRUE"

        count_row = self.db.execute_one(
            f"SELECT COUNT(*) as total FROM audit_log a WHERE {where_clause}",
            tuple(params),
        )
        total = count_row["total"] if count_row else 0

        query_params = list(params)
        query_params.extend([limit, offset])

        rows = self.db.execute(
            f"""
            SELECT a.id, a.trace_id, a.actor, a.entry_point, a.action,
                   a.resource_type, a.resource_id, a.project_id,
                   a.session_name, a.before_state, a.after_state,
                   a.metadata, a.created_at, p.name as project
            FROM audit_log a
            LEFT JOIN projects p ON a.project_id = p.id
            WHERE {where_clause}
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(query_params),
        )

        items = [
            {
                "id": r["id"],
                "trace_id": r["trace_id"],
                "actor": r["actor"],
                "entry_point": r["entry_point"],
                "action": r["action"],
                "resource_type": r["resource_type"],
                "resource_id": r["resource_id"],
                "project": r["project"],
                "session_name": r["session_name"],
                "before_state": r["before_state"],
                "after_state": r["after_state"],
                "metadata": r["metadata"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def get(self, audit_id: int) -> dict | None:
        """Get a single audit entry by ID."""
        row = self.db.execute_one(
            """
            SELECT a.id, a.trace_id, a.actor, a.entry_point, a.action,
                   a.resource_type, a.resource_id, a.project_id,
                   a.session_name, a.before_state, a.after_state,
                   a.metadata, a.created_at, p.name as project
            FROM audit_log a
            LEFT JOIN projects p ON a.project_id = p.id
            WHERE a.id = %s
            """,
            (audit_id,),
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "trace_id": row["trace_id"],
            "actor": row["actor"],
            "entry_point": row["entry_point"],
            "action": row["action"],
            "resource_type": row["resource_type"],
            "resource_id": row["resource_id"],
            "project": row["project"],
            "session_name": row["session_name"],
            "before_state": row["before_state"],
            "after_state": row["after_state"],
            "metadata": row["metadata"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
