"""Structured thinking: goal-oriented reasoning sequences with branching."""

from __future__ import annotations

import logging

from cairn.storage.database import Database

logger = logging.getLogger(__name__)

VALID_THOUGHT_TYPES = [
    "observation", "hypothesis", "question", "reasoning", "conclusion",
    "assumption", "analysis", "general", "alternative", "branch",
]


class ThinkingEngine:
    """Manages structured thinking sequences."""

    def __init__(self, db: Database):
        self.db = db

    def _resolve_project_id(self, project_name: str) -> int:
        """Get or create a project by name. Returns project ID."""
        row = self.db.execute_one(
            "SELECT id FROM projects WHERE name = %s", (project_name,)
        )
        if row:
            return row["id"]

        row = self.db.execute_one(
            "INSERT INTO projects (name) VALUES (%s) RETURNING id",
            (project_name,),
        )
        self.db.commit()
        return row["id"]

    def start(self, project: str, goal: str) -> dict:
        """Start a new thinking sequence."""
        project_id = self._resolve_project_id(project)

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
            "status": "active",
            "created_at": row["created_at"].isoformat(),
        }

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
        if seq["status"] != "active":
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

    def conclude(self, sequence_id: int, conclusion: str) -> dict:
        """Conclude a thinking sequence. Adds final thought and marks complete."""
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

    def list_sequences(self, project: str, status: str | None = None) -> list[dict]:
        """List thinking sequences for a project."""
        project_id = self._resolve_project_id(project)

        if status:
            rows = self.db.execute(
                """
                SELECT ts.id, ts.goal, ts.status, ts.created_at, ts.completed_at,
                       COUNT(t.id) as thought_count
                FROM thinking_sequences ts
                LEFT JOIN thoughts t ON t.sequence_id = ts.id
                WHERE ts.project_id = %s AND ts.status = %s
                GROUP BY ts.id
                ORDER BY ts.created_at DESC
                """,
                (project_id, status),
            )
        else:
            rows = self.db.execute(
                """
                SELECT ts.id, ts.goal, ts.status, ts.created_at, ts.completed_at,
                       COUNT(t.id) as thought_count
                FROM thinking_sequences ts
                LEFT JOIN thoughts t ON t.sequence_id = ts.id
                WHERE ts.project_id = %s
                GROUP BY ts.id
                ORDER BY ts.created_at DESC
                """,
                (project_id,),
            )

        return [
            {
                "sequence_id": r["id"],
                "goal": r["goal"],
                "status": r["status"],
                "thought_count": r["thought_count"],
                "created_at": r["created_at"].isoformat(),
                "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            }
            for r in rows
        ]
