"""Agent persistent memory — compound learning across dispatches (ca-158).

Gives agents a persistent memory layer that accumulates learnings across
work items and sessions. When an agent is dispatched, its relevant past
learnings are injected into the briefing, creating compound knowledge.

Learnings are stored as tagged memories with agent attribution, enabling:
- Pattern recognition across similar tasks
- Mistake avoidance (learning from past errors)
- Convention enforcement (remembering project-specific practices)
- Skill transfer between agents working on the same project

Storage is backed by the existing Cairn memory system — learnings are
just memories with agent-specific metadata.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.analytics import track_operation
from cairn.core.utils import get_or_create_project, get_project

if TYPE_CHECKING:
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class AgentMemoryStore:
    """Persistent learning store for agents.

    Wraps the memory system with agent-specific tagging and retrieval.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    @track_operation("agent_memory.store_learning")
    def store_learning(
        self,
        agent_name: str,
        project: str,
        content: str,
        *,
        work_item_id: str | None = None,
        learning_type: str = "general",
        importance: float = 0.6,
    ) -> dict:
        """Store a learning from an agent's work.

        Args:
            agent_name: The agent that learned this.
            project: Project context.
            content: The learning content.
            work_item_id: Display ID of the work item that produced this learning.
            learning_type: Category — general, mistake, convention, pattern, optimization.
            importance: 0.0 to 1.0 priority.
        """
        project_id = get_or_create_project(self.db, project)

        row = self.db.execute_one(
            """
            INSERT INTO agent_learnings
                (agent_name, project_id, content, work_item_display_id,
                 learning_type, importance)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (agent_name, project_id, content, work_item_id, learning_type, importance),
        )
        assert row is not None
        self.db.commit()

        logger.info(
            "Stored learning #%d for agent '%s' (project: %s, type: %s)",
            row["id"], agent_name, project, learning_type,
        )
        return {
            "id": row["id"],
            "agent_name": agent_name,
            "project": project,
            "learning_type": learning_type,
            "stored": True,
        }

    @track_operation("agent_memory.recall_learnings")
    def recall_learnings(
        self,
        agent_name: str,
        project: str | None = None,
        *,
        learning_type: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Retrieve learnings for an agent, ordered by importance and recency.

        Args:
            agent_name: The agent to retrieve learnings for.
            project: Optional project filter.
            learning_type: Optional type filter.
            limit: Max learnings to return.
        """
        conditions = ["al.agent_name = %s", "al.active = TRUE"]
        params: list = [agent_name]

        if project:
            project_id = get_project(self.db, project)
            if project_id is None:
                return []
            conditions.append("al.project_id = %s")
            params.append(project_id)

        if learning_type:
            conditions.append("al.learning_type = %s")
            params.append(learning_type)

        where = " AND ".join(conditions)
        params.append(limit)

        rows = self.db.execute(
            f"""
            SELECT al.id, al.agent_name, al.content, al.learning_type,
                   al.importance, al.work_item_display_id,
                   al.created_at, p.name as project
            FROM agent_learnings al
            LEFT JOIN projects p ON al.project_id = p.id
            WHERE {where}
            ORDER BY al.importance DESC, al.created_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return [
            {
                "id": r["id"],
                "agent_name": r["agent_name"],
                "content": r["content"],
                "learning_type": r["learning_type"],
                "importance": float(r["importance"]),
                "work_item_id": r["work_item_display_id"],
                "project": r["project"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]

    @track_operation("agent_memory.deactivate")
    def deactivate_learning(self, learning_id: int, reason: str = "") -> dict:
        """Soft-delete a learning (mark inactive)."""
        self.db.execute(
            "UPDATE agent_learnings SET active = FALSE WHERE id = %s",
            (learning_id,),
        )
        self.db.commit()
        return {"id": learning_id, "active": False, "reason": reason}

    def briefing_context(
        self,
        agent_name: str,
        project: str,
        limit: int = 5,
    ) -> list[dict]:
        """Get learnings formatted for injection into agent briefings.

        Returns a concise list suitable for prepending to dispatch briefings.
        """
        learnings = self.recall_learnings(agent_name, project, limit=limit)
        return [
            {
                "type": l["learning_type"],
                "content": l["content"],
                "source": l.get("work_item_id") or "",
            }
            for l in learnings
        ]

    @track_operation("agent_memory.extract_from_deliverable")
    def extract_from_deliverable(
        self,
        agent_name: str,
        project: str,
        deliverable: dict,
        work_item_id: str | None = None,
    ) -> list[dict]:
        """Extract and store learnings from a completed deliverable.

        Pulls learnings from deliverable metadata keys: decisions,
        open_items, and any explicit 'learnings' field.
        """
        stored: list[dict] = []

        # Store decisions as convention learnings
        decisions = deliverable.get("decisions") or deliverable.get("metadata", {}).get("decisions", [])
        if isinstance(decisions, list):
            for decision in decisions:
                text = decision if isinstance(decision, str) else decision.get("content", str(decision))
                if text:
                    result = self.store_learning(
                        agent_name, project, f"Decision: {text}",
                        work_item_id=work_item_id,
                        learning_type="convention",
                        importance=0.7,
                    )
                    stored.append(result)

        # Store explicit learnings
        learnings = deliverable.get("learnings") or deliverable.get("metadata", {}).get("learnings", [])
        if isinstance(learnings, list):
            for learning in learnings:
                text = learning if isinstance(learning, str) else learning.get("content", str(learning))
                if text:
                    result = self.store_learning(
                        agent_name, project, text,
                        work_item_id=work_item_id,
                        learning_type="general",
                        importance=0.6,
                    )
                    stored.append(result)

        return stored
