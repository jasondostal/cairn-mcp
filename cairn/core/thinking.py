"""Structured thinking: goal-oriented reasoning sequences with branching."""

from __future__ import annotations

import logging

from cairn.core.analytics import track_operation
from cairn.core.constants import VALID_THOUGHT_TYPES, ThinkingStatus
from cairn.core.utils import get_or_create_project, get_project
from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class ThinkingEngine:
    """Manages structured thinking sequences."""

    def __init__(self, db: Database):
        self.db = db

    @track_operation("think.start")
    def start(self, project: str, goal: str) -> dict:
        """Start a new thinking sequence."""
        project_id = get_or_create_project(self.db,project)

        row = self.db.execute_one(
            """
            INSERT INTO thinking_sequences (project_id, goal)
            VALUES (%s, %s)
            RETURNING id, created_at
            """,
            (project_id, goal),
        )
        self.db.commit()

        logger.info("Started thinking sequence #%d: %s", row["id"], goal[:80])
        return {
            "sequence_id": row["id"],
            "project": project,
            "goal": goal,
            "status": ThinkingStatus.ACTIVE,
            "created_at": row["created_at"].isoformat(),
        }

    @track_operation("think.add")
    def add_thought(
        self,
        sequence_id: int,
        thought: str,
        thought_type: str = "general",
        branch_name: str | None = None,
    ) -> dict:
        """Add a thought to an active sequence."""
        # Verify sequence exists and is active
        seq = self.db.execute_one(
            "SELECT id, status FROM thinking_sequences WHERE id = %s",
            (sequence_id,),
        )
        if not seq:
            raise ValueError(f"Thinking sequence {sequence_id} not found")
        if seq["status"] != ThinkingStatus.ACTIVE:
            raise ValueError(f"Thinking sequence {sequence_id} is {seq['status']}, cannot add thoughts")

        # Normalize thought type
        if thought_type not in VALID_THOUGHT_TYPES:
            thought_type = "general"

        # Branch types create a new branch
        is_branch = thought_type in ("alternative", "branch")

        row = self.db.execute_one(
            """
            INSERT INTO thoughts (sequence_id, thought_type, content, branch_name)
            VALUES (%s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (sequence_id, thought_type, thought, branch_name if is_branch else None),
        )
        self.db.commit()

        return {
            "thought_id": row["id"],
            "sequence_id": sequence_id,
            "thought_type": thought_type,
            "branch_name": branch_name if is_branch else None,
            "created_at": row["created_at"].isoformat(),
        }

    @track_operation("think.conclude")
    def conclude(self, sequence_id: int, conclusion: str) -> dict:
        """Conclude a thinking sequence. Adds final thought and marks complete."""
        # Guard: check sequence exists and is still active
        seq = self.db.execute_one(
            "SELECT id, status FROM thinking_sequences WHERE id = %s",
            (sequence_id,),
        )
        if not seq:
            raise ValueError(f"Thinking sequence {sequence_id} not found")
        if seq["status"] != ThinkingStatus.ACTIVE:
            raise ValueError(f"Thinking sequence {sequence_id} is already {seq['status']}")

        # Add the conclusion thought
        self.add_thought(sequence_id, conclusion, thought_type="conclusion")

        # Mark sequence as completed
        self.db.execute(
            """
            UPDATE thinking_sequences
            SET status = 'completed', completed_at = NOW()
            WHERE id = %s
            """,
            (sequence_id,),
        )
        self.db.commit()

        # Return the full sequence
        return self.get_sequence(sequence_id)

    @track_operation("think.get")
    def get_sequence(self, sequence_id: int) -> dict:
        """Get a full thinking sequence with all thoughts."""
        seq = self.db.execute_one(
            """
            SELECT ts.id, ts.goal, ts.status, ts.created_at, ts.completed_at,
                   p.name as project
            FROM thinking_sequences ts
            LEFT JOIN projects p ON ts.project_id = p.id
            WHERE ts.id = %s
            """,
            (sequence_id,),
        )
        if not seq:
            raise ValueError(f"Thinking sequence {sequence_id} not found")

        thoughts = self.db.execute(
            """
            SELECT id, thought_type, content, branch_name, created_at
            FROM thoughts
            WHERE sequence_id = %s
            ORDER BY created_at
            """,
            (sequence_id,),
        )

        return {
            "sequence_id": seq["id"],
            "project": seq["project"],
            "goal": seq["goal"],
            "status": seq["status"],
            "created_at": seq["created_at"].isoformat(),
            "completed_at": seq["completed_at"].isoformat() if seq["completed_at"] else None,
            "thoughts": [
                {
                    "id": t["id"],
                    "type": t["thought_type"],
                    "content": t["content"],
                    "branch": t["branch_name"],
                    "created_at": t["created_at"].isoformat(),
                }
                for t in thoughts
            ],
        }

    @track_operation("think.list")
    def list_sequences(
        self, project: str | list[str] | None = None, status: str | None = None,
        limit: int | None = None, offset: int = 0,
    ) -> dict:
        """List thinking sequences for project(s) (or all projects) with optional pagination.

        Returns dict with 'total', 'limit', 'offset', and 'items' keys.
        """
        if project is not None:
            if isinstance(project, list):
                where = "p.name = ANY(%s)"
                base_params: list = [project]
            else:
                project_id = get_project(self.db, project)
                if project_id is None:
                    return {"total": 0, "limit": limit, "offset": offset, "items": []}
                where = "ts.project_id = %s"
                base_params = [project_id]
        else:
            where = "TRUE"
            base_params = []

        status_filter = " AND ts.status = %s" if status else ""
        count_params: list = list(base_params)
        if status:
            count_params.append(status)

        count_join = " LEFT JOIN projects p ON ts.project_id = p.id" if isinstance(project, list) else ""
        count_row = self.db.execute_one(
            f"SELECT COUNT(*) as total FROM thinking_sequences ts{count_join} WHERE {where}{status_filter}",
            tuple(count_params),
        )
        total = count_row["total"]

        query = f"""
            SELECT ts.id, ts.goal, ts.status, ts.created_at, ts.completed_at,
                   p.name as project,
                   COUNT(t.id) as thought_count
            FROM thinking_sequences ts
            LEFT JOIN thoughts t ON t.sequence_id = ts.id
            LEFT JOIN projects p ON ts.project_id = p.id
            WHERE {where}{status_filter}
            GROUP BY ts.id, p.name
            ORDER BY ts.created_at DESC
        """
        params: list = list(count_params)

        if limit is not None:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])

        rows = self.db.execute(query, tuple(params))

        items = [
            {
                "sequence_id": r["id"],
                "goal": r["goal"],
                "status": r["status"],
                "project": r["project"],
                "thought_count": r["thought_count"],
                "created_at": r["created_at"].isoformat(),
                "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}
