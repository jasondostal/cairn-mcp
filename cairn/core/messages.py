"""Message layer: inter-agent communication for agents and the user."""

from __future__ import annotations

import logging

from cairn.core.analytics import track_operation
from cairn.core.utils import get_or_create_project, get_project
from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class MessageManager:
    """Handles sending, reading, and managing messages between agents and the user."""

    def __init__(self, db: Database):
        self.db = db

    @track_operation("messages.send")
    def send(
        self,
        content: str,
        project: str,
        sender: str = "assistant",
        priority: str = "normal",
        metadata: dict | None = None,
    ) -> dict:
        """Send a message."""
        if priority not in ("normal", "urgent"):
            raise ValueError(f"Invalid priority: {priority}. Must be 'normal' or 'urgent'.")

        project_id = get_or_create_project(self.db, project)

        row = self.db.execute_one(
            """
            INSERT INTO messages (project_id, sender, content, priority, metadata)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            RETURNING id, created_at
            """,
            (project_id, sender, content, priority, __import__("json").dumps(metadata or {})),
        )
        self.db.commit()

        logger.info("Message #%d sent by %s to project %s", row["id"], sender, project)
        return {
            "id": row["id"],
            "project": project,
            "sender": sender,
            "priority": priority,
            "created_at": row["created_at"].isoformat(),
        }

    @track_operation("messages.inbox")
    def inbox(
        self,
        project: str | list[str] | None = None,
        include_archived: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Get inbox messages, newest first, unread on top."""
        where_parts = []
        params: list = []

        if not include_archived:
            where_parts.append("m.archived = false")

        if project is not None:
            if isinstance(project, list):
                where_parts.append("p.name = ANY(%s)")
                params.append(project)
            else:
                project_id = get_project(self.db, project)
                if project_id is None:
                    return {"total": 0, "limit": limit, "offset": offset, "items": []}
                where_parts.append("m.project_id = %s")
                params.append(project_id)

        where_clause = " AND ".join(where_parts) if where_parts else "TRUE"

        count_row = self.db.execute_one(
            f"""
            SELECT COUNT(*) as total FROM messages m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where_clause}
            """,
            tuple(params),
        )
        total = count_row["total"]

        query_params = list(params)
        query_params.extend([limit, offset])

        rows = self.db.execute(
            f"""
            SELECT m.id, m.sender, m.content, m.priority, m.is_read, m.archived,
                   m.metadata, m.created_at, m.updated_at,
                   p.name as project
            FROM messages m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where_clause}
            ORDER BY m.is_read ASC, m.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(query_params),
        )

        items = [
            {
                "id": r["id"],
                "project": r["project"],
                "sender": r["sender"],
                "content": r["content"],
                "priority": r["priority"],
                "is_read": r["is_read"],
                "archived": r["archived"],
                "metadata": r["metadata"] or {},
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]

        return {"total": total, "limit": limit, "offset": offset, "items": items}

    @track_operation("messages.mark_read")
    def mark_read(self, message_id: int) -> dict:
        """Mark a single message as read."""
        self.db.execute(
            "UPDATE messages SET is_read = true, updated_at = NOW() WHERE id = %s",
            (message_id,),
        )
        self.db.commit()
        return {"id": message_id, "is_read": True}

    @track_operation("messages.mark_all_read")
    def mark_all_read(self, project: str | None = None) -> dict:
        """Mark all unread messages as read, optionally filtered by project."""
        if project:
            project_id = get_project(self.db, project)
            if project_id is None:
                return {"updated": 0}
            self.db.execute(
                "UPDATE messages SET is_read = true, updated_at = NOW() WHERE is_read = false AND project_id = %s",
                (project_id,),
            )
        else:
            self.db.execute(
                "UPDATE messages SET is_read = true, updated_at = NOW() WHERE is_read = false",
            )
        self.db.commit()
        return {"action": "mark_all_read", "project": project}

    @track_operation("messages.archive")
    def archive(self, message_id: int) -> dict:
        """Archive a message (soft-remove from inbox)."""
        self.db.execute(
            "UPDATE messages SET archived = true, updated_at = NOW() WHERE id = %s",
            (message_id,),
        )
        self.db.commit()
        return {"id": message_id, "archived": True}

    @track_operation("messages.unread_count")
    def unread_count(self, project: str | None = None) -> int:
        """Fast count of unread, non-archived messages."""
        if project:
            project_id = get_project(self.db, project)
            if project_id is None:
                return 0
            row = self.db.execute_one(
                "SELECT COUNT(*) as count FROM messages WHERE is_read = false AND archived = false AND project_id = %s",
                (project_id,),
            )
        else:
            row = self.db.execute_one(
                "SELECT COUNT(*) as count FROM messages WHERE is_read = false AND archived = false",
            )
        return row["count"]
