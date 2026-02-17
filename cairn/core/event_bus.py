"""EventBus — lightweight event publishing and query.

Replaces the DigestWorker pipeline. Individual events are INSERTed into the
events table (triggering Postgres NOTIFY for real-time streaming). No LLM
in the hot path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cairn.core.utils import get_or_create_project

if TYPE_CHECKING:
    from cairn.core.projects import ProjectManager
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class EventBus:
    """Central publish point for the event bus.

    Both API endpoints and internal callers use this to insert events
    and manage sessions.
    """

    def __init__(self, db: Database, project_manager: ProjectManager):
        self.db = db
        self.project_manager = project_manager

    def publish(
        self,
        session_name: str,
        event_type: str,
        *,
        project: str | None = None,
        agent_id: str | None = None,
        work_item_id: int | None = None,
        tool_name: str | None = None,
        payload: dict | None = None,
    ) -> int:
        """Insert event and trigger NOTIFY. Returns event id.

        Lifecycle side-effects:
        - session_start events auto-create a session record (upsert).
        - session_end events auto-close the session (set closed_at).
        """
        import json

        project_id = None
        if project:
            project_id = get_or_create_project(self.db, project)

        row = self.db.execute_one(
            """
            INSERT INTO events
                (session_name, agent_id, work_item_id, project_id,
                 event_type, tool_name, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                session_name,
                agent_id,
                work_item_id,
                project_id,
                event_type,
                tool_name,
                json.dumps(payload or {}),
            ),
        )
        self.db.commit()

        event_id = row["id"]
        logger.debug(
            "Event published: id=%d session=%s type=%s tool=%s",
            event_id, session_name, event_type, tool_name,
        )

        # Auto-manage session lifecycle from events
        _payload = payload or {}
        if event_type == "session_start" and project:
            try:
                self.open_session(
                    session_name=session_name,
                    project=project,
                    agent_id=agent_id,
                    agent_type=_payload.get("agent_type", "interactive"),
                    parent_session=_payload.get("parent_session"),
                )
            except Exception:
                logger.warning("Auto open_session failed for %s", session_name, exc_info=True)
        elif event_type == "session_end":
            try:
                self.close_session(session_name)
            except Exception:
                logger.warning("Auto close_session failed for %s", session_name, exc_info=True)

        return event_id

    def query(
        self,
        *,
        session_name: str | None = None,
        work_item_id: int | None = None,
        event_type: str | None = None,
        project: str | None = None,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc",
    ) -> dict:
        """Query events with filters."""
        where_parts = []
        params: list = []

        if session_name:
            where_parts.append("e.session_name = %s")
            params.append(session_name)
        if work_item_id is not None:
            where_parts.append("e.work_item_id = %s")
            params.append(work_item_id)
        if event_type:
            where_parts.append("e.event_type = %s")
            params.append(event_type)
        if project:
            where_parts.append("p.name = %s")
            params.append(project)

        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        order_dir = "ASC" if order == "asc" else "DESC"

        rows = self.db.execute(
            f"""
            SELECT e.id, e.session_name, e.agent_id, e.work_item_id,
                   e.event_type, e.tool_name, e.payload,
                   e.created_at, p.name as project
            FROM events e
            LEFT JOIN projects p ON e.project_id = p.id
            {where_clause}
            ORDER BY e.created_at {order_dir}
            LIMIT %s OFFSET %s
            """,
            tuple(params) + (limit, offset),
        )

        items = [
            {
                "id": r["id"],
                "session_name": r["session_name"],
                "agent_id": r["agent_id"],
                "work_item_id": r["work_item_id"],
                "event_type": r["event_type"],
                "tool_name": r["tool_name"],
                "payload": r["payload"],
                "project": r["project"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

        return {"count": len(items), "items": items}

    def open_session(
        self,
        session_name: str,
        project: str,
        agent_id: str | None = None,
        agent_type: str = "interactive",
        parent_session: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create session record. Upserts on session_name."""
        import json

        project_id = get_or_create_project(self.db, project)

        row = self.db.execute_one(
            """
            INSERT INTO sessions
                (session_name, project_id, agent_id, agent_type,
                 parent_session, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (session_name) DO UPDATE SET
                project_id = EXCLUDED.project_id,
                agent_id = COALESCE(EXCLUDED.agent_id, sessions.agent_id),
                agent_type = EXCLUDED.agent_type,
                metadata = sessions.metadata || EXCLUDED.metadata
            RETURNING id, session_name, started_at
            """,
            (
                session_name,
                project_id,
                agent_id,
                agent_type,
                parent_session,
                json.dumps(metadata or {}),
            ),
        )
        self.db.commit()

        return {
            "id": row["id"],
            "session_name": row["session_name"],
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        }

    def close_session(self, session_name: str) -> dict:
        """Set closed_at on the session. No LLM."""
        now = datetime.now(timezone.utc)

        row = self.db.execute_one(
            """
            UPDATE sessions
            SET closed_at = %s
            WHERE session_name = %s AND closed_at IS NULL
            RETURNING id, session_name, started_at, closed_at
            """,
            (now, session_name),
        )
        self.db.commit()

        if not row:
            return {"session_name": session_name, "status": "already_closed"}

        return {
            "session_name": row["session_name"],
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "closed_at": row["closed_at"].isoformat() if row["closed_at"] else None,
            "status": "closed",
        }

    def list_sessions(
        self,
        *,
        project: str | None = None,
        active_only: bool = False,
        limit: int = 20,
    ) -> dict:
        """List sessions from the sessions table."""
        where_parts = []
        params: list = []

        if project:
            where_parts.append("p.name = %s")
            params.append(project)
        if active_only:
            where_parts.append("s.closed_at IS NULL")

        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        rows = self.db.execute(
            f"""
            SELECT s.id, s.session_name, s.agent_id, s.agent_type,
                   s.parent_session, s.started_at, s.closed_at,
                   s.metadata, p.name as project,
                   (SELECT COUNT(*) FROM events e WHERE e.session_name = s.session_name) as event_count
            FROM sessions s
            LEFT JOIN projects p ON s.project_id = p.id
            {where_clause}
            ORDER BY s.started_at DESC
            LIMIT %s
            """,
            tuple(params) + (limit,),
        )

        items = [
            {
                "id": r["id"],
                "session_name": r["session_name"],
                "agent_id": r["agent_id"],
                "agent_type": r["agent_type"],
                "parent_session": r["parent_session"],
                "project": r["project"],
                "event_count": r["event_count"],
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                "closed_at": r["closed_at"].isoformat() if r["closed_at"] else None,
                "is_active": r["closed_at"] is None,
            }
            for r in rows
        ]

        return {"count": len(items), "items": items}
