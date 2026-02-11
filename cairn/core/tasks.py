"""Task management: create, complete, list, link memories."""

from __future__ import annotations

import logging

from cairn.core.constants import TaskStatus
from cairn.core.utils import get_or_create_project, get_project
from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class TaskManager:
    """Handles task lifecycle and memory linking."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, project: str, description: str) -> dict:
        """Create a new task."""
        project_id = get_or_create_project(self.db,project)

        row = self.db.execute_one(
            """
            INSERT INTO tasks (project_id, description)
            VALUES (%s, %s)
            RETURNING id, created_at
            """,
            (project_id, description),
        )
        self.db.commit()

        logger.info("Created task #%d for project %s", row["id"], project)
        return {
            "id": row["id"],
            "project": project,
            "description": description,
            "status": TaskStatus.PENDING,
            "created_at": row["created_at"].isoformat(),
        }

    def complete(self, task_id: int) -> dict:
        """Mark a task as completed."""
        self.db.execute(
            "UPDATE tasks SET status = 'completed', completed_at = NOW() WHERE id = %s",
            (task_id,),
        )
        self.db.commit()
        return {"id": task_id, "action": "completed"}

    def list_tasks(
        self, project: str | list[str] | None = None, include_completed: bool = False,
        limit: int | None = None, offset: int = 0,
    ) -> dict:
        """List tasks for project(s) (or all projects) with optional pagination.

        Returns dict with 'total', 'limit', 'offset', and 'items' keys.
        """
        status_filter = "" if include_completed else f" AND t.status = '{TaskStatus.PENDING}'"

        if project is not None:
            if isinstance(project, list):
                where = "p.name = ANY(%s)"
                base_params: list = [project]
            else:
                project_id = get_project(self.db, project)
                if project_id is None:
                    return {"total": 0, "limit": limit, "offset": offset, "items": []}
                where = "t.project_id = %s"
                base_params = [project_id]
        else:
            where = "TRUE"
            base_params = []

        # Get total count
        count_join = " LEFT JOIN projects p ON t.project_id = p.id" if isinstance(project, list) else ""
        count_row = self.db.execute_one(
            f"SELECT COUNT(*) as total FROM tasks t{count_join} WHERE {where}{status_filter}",
            tuple(base_params),
        )
        total = count_row["total"]

        query = f"""
            SELECT t.id, t.description, t.status, t.created_at, t.completed_at,
                   p.name as project,
                   array_agg(tml.memory_id) FILTER (WHERE tml.memory_id IS NOT NULL) as linked_memories
            FROM tasks t
            LEFT JOIN task_memory_links tml ON tml.task_id = t.id
            LEFT JOIN projects p ON t.project_id = p.id
            WHERE {where}{status_filter}
            GROUP BY t.id, p.name
            ORDER BY t.created_at DESC
        """
        params: list = list(base_params)

        if limit is not None:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])

        rows = self.db.execute(query, tuple(params))

        items = [
            {
                "id": r["id"],
                "description": r["description"],
                "status": r["status"],
                "project": r["project"],
                "linked_memories": r["linked_memories"] or [],
                "created_at": r["created_at"].isoformat(),
                "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def link_memories(self, task_id: int, memory_ids: list[int]) -> dict:
        """Link memories to a task."""
        for mid in memory_ids:
            self.db.execute(
                """
                INSERT INTO task_memory_links (task_id, memory_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (task_id, mid),
            )
        self.db.commit()

        return {"task_id": task_id, "linked": memory_ids}
