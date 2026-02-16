"""Structured thinking: goal-oriented reasoning sequences with branching."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.analytics import track_operation
from cairn.core.constants import VALID_THOUGHT_TYPES, ThinkingStatus
from cairn.core.utils import get_or_create_project, get_project
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.core.extraction import KnowledgeExtractor
    from cairn.embedding.interface import EmbeddingInterface
    from cairn.graph.interface import GraphProvider

logger = logging.getLogger(__name__)


class ThinkingEngine:
    """Manages structured thinking sequences."""

    def __init__(
        self,
        db: Database,
        graph: GraphProvider | None = None,
        knowledge_extractor: KnowledgeExtractor | None = None,
        embedding: EmbeddingInterface | None = None,
        thought_extraction: str = "off",
    ):
        self.db = db
        self.graph = graph
        self.knowledge_extractor = knowledge_extractor
        self.embedding = embedding
        self.thought_extraction = thought_extraction

    def _graph_sync_sequence(self, pg_id: int, project_id: int, goal: str) -> None:
        """Dual-write: create ThinkingSequence node in graph, update PG sync columns."""
        if not self.graph:
            return
        try:
            graph_uuid = self.graph.create_thinking_sequence(
                pg_id=pg_id, project_id=project_id, goal=goal,
            )
            self.db.execute(
                "UPDATE thinking_sequences SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                (graph_uuid, pg_id),
            )
            self.db.commit()
        except Exception:
            logger.warning("Graph sync failed for thinking_sequence #%d", pg_id, exc_info=True)

    def _graph_sync_thought(self, pg_id: int, sequence_id: int, thought_type: str, content: str) -> None:
        """Dual-write: create Thought node in graph, link via CONTAINS."""
        if not self.graph:
            return
        try:
            seq_row = self.db.execute_one(
                "SELECT graph_uuid FROM thinking_sequences WHERE id = %s",
                (sequence_id,),
            )
            if not seq_row or not seq_row["graph_uuid"]:
                return
            content_embedding = None
            if self.embedding:
                try:
                    content_embedding = self.embedding.embed(content[:500])
                except Exception:
                    pass
            graph_uuid = self.graph.create_thought(
                pg_id=pg_id,
                sequence_uuid=seq_row["graph_uuid"],
                thought_type=thought_type,
                content=content,
                content_embedding=content_embedding,
            )
            self.db.execute(
                "UPDATE thoughts SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                (graph_uuid, pg_id),
            )
            self.db.commit()
        except Exception:
            logger.warning("Graph sync failed for thought #%d", pg_id, exc_info=True)

    def _run_extraction(self, sequence_id: int, content: str) -> None:
        """Run entity extraction on content and link results to the sequence."""
        if not self.knowledge_extractor:
            return
        try:
            seq = self.db.execute_one(
                """SELECT ts.project_id, ts.graph_uuid
                   FROM thinking_sequences ts WHERE ts.id = %s""",
                (sequence_id,),
            )
            if not seq:
                return
            known = []
            if self.graph:
                try:
                    known = self.graph.get_known_entities(seq["project_id"], limit=100)
                except Exception:
                    pass
            result = self.knowledge_extractor.extract(
                content, known_entities=known or None,
            )
            if result and (result.entities or result.statements):
                stats = self.knowledge_extractor.resolve_and_persist(
                    result, episode_id=0, project_id=seq["project_id"],
                )
                logger.info(
                    "Thought extraction: %d entities, %d statements (sequence #%d)",
                    stats.get("entities_created", 0) + stats.get("entities_merged", 0),
                    stats.get("statements_created", 0),
                    sequence_id,
                )
        except Exception:
            logger.warning("Thought extraction failed for sequence #%d", sequence_id, exc_info=True)

    @track_operation("think.start")
    def start(self, project: str, goal: str) -> dict:
        """Start a new thinking sequence."""
        project_id = get_or_create_project(self.db, project)

        row = self.db.execute_one(
            """
            INSERT INTO thinking_sequences (project_id, goal)
            VALUES (%s, %s)
            RETURNING id, created_at
            """,
            (project_id, goal),
        )
        self.db.commit()

        # Dual-write to graph
        self._graph_sync_sequence(row["id"], project_id, goal)

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

        # Dual-write to graph
        self._graph_sync_thought(row["id"], sequence_id, thought_type, thought)

        # Entity extraction on every thought (if configured)
        if self.thought_extraction == "on_every_thought":
            self._run_extraction(sequence_id, thought)

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

        # Mark complete in graph
        if self.graph:
            try:
                seq_row = self.db.execute_one(
                    "SELECT graph_uuid FROM thinking_sequences WHERE id = %s",
                    (sequence_id,),
                )
                if seq_row and seq_row["graph_uuid"]:
                    self.graph.complete_thinking_sequence(seq_row["graph_uuid"])
            except Exception:
                logger.warning("Graph complete failed for sequence #%d", sequence_id, exc_info=True)

        # Entity extraction on conclude (if configured)
        if self.thought_extraction == "on_conclude":
            thoughts = self.db.execute(
                "SELECT content FROM thoughts WHERE sequence_id = %s ORDER BY created_at",
                (sequence_id,),
            )
            all_content = "\n\n".join(t["content"] for t in thoughts)
            self._run_extraction(sequence_id, all_content)

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
