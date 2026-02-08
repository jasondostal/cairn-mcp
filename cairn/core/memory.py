"""Core memory operations: store, retrieve, modify."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cairn.embedding.engine import EmbeddingEngine
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.core.enrichment import Enricher

logger = logging.getLogger(__name__)


class MemoryStore:
    """Handles all memory CRUD operations."""

    def __init__(self, db: Database, embedding: EmbeddingEngine, enricher: Enricher | None = None):
        self.db = db
        self.embedding = embedding
        self.enricher = enricher

    def _resolve_project_id(self, project_name: str) -> int:
        """Get or create a project by name. Returns project ID."""
        row = self.db.execute_one(
            "SELECT id FROM projects WHERE name = %s",
            (project_name,),
        )
        if row:
            return row["id"]

        row = self.db.execute_one(
            "INSERT INTO projects (name) VALUES (%s) RETURNING id",
            (project_name,),
        )
        self.db.commit()
        return row["id"]

    def store(
        self,
        content: str,
        project: str,
        memory_type: str = "note",
        importance: float = 0.5,
        tags: list[str] | None = None,
        session_name: str | None = None,
        related_files: list[str] | None = None,
        related_ids: list[int] | None = None,
    ) -> dict:
        """Store a memory with embedding.

        Returns the stored memory dict with ID.
        """
        project_id = self._resolve_project_id(project)

        # Generate embedding
        vector = self.embedding.embed(content)

        # --- Enrichment ---
        enrichment = {}
        if self.enricher:
            enrichment = self.enricher.enrich(content)

        # Override logic: caller-provided values win
        # Tags: caller tags stay in `tags`, LLM tags go to `auto_tags`
        auto_tags = enrichment.get("tags", [])
        caller_tags = tags or []

        # Importance: caller wins if not the default 0.5
        final_importance = importance
        if importance == 0.5 and "importance" in enrichment:
            final_importance = enrichment["importance"]

        # Memory type: caller wins if not the default "note"
        final_type = memory_type
        if memory_type == "note" and "memory_type" in enrichment:
            final_type = enrichment["memory_type"]

        # Summary: always from LLM
        summary = enrichment.get("summary")

        # Insert memory
        row = self.db.execute_one(
            """
            INSERT INTO memories
                (content, memory_type, importance, project_id, session_name,
                 embedding, tags, auto_tags, summary, related_files)
            VALUES
                (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (
                content,
                final_type,
                final_importance,
                project_id,
                session_name,
                str(vector),
                caller_tags,
                auto_tags,
                summary,
                related_files or [],
            ),
        )

        memory_id = row["id"]

        # Create relationships if specified
        if related_ids:
            for related_id in related_ids:
                self.db.execute(
                    """
                    INSERT INTO memory_relations (source_id, target_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (memory_id, related_id),
                )

        self.db.commit()

        logger.info("Stored memory #%d (type=%s, project=%s)", memory_id, final_type, project)

        return {
            "id": memory_id,
            "content": content,
            "memory_type": final_type,
            "importance": final_importance,
            "project": project,
            "tags": caller_tags,
            "auto_tags": auto_tags,
            "summary": summary,
            "created_at": row["created_at"].isoformat(),
        }

    def recall(self, ids: list[int]) -> list[dict]:
        """Retrieve full content for one or more memory IDs."""
        if not ids:
            return []

        placeholders = ",".join(["%s"] * len(ids))
        rows = self.db.execute(
            f"""
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.related_files, m.is_active,
                   m.inactive_reason, m.session_name,
                   m.created_at, m.updated_at,
                   p.name as project,
                   c.id as cluster_id, c.label as cluster_label,
                   c.member_count as cluster_size
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            LEFT JOIN cluster_members cm ON cm.memory_id = m.id
            LEFT JOIN clusters c ON c.id = cm.cluster_id
            WHERE m.id IN ({placeholders})
            ORDER BY m.id
            """,
            tuple(ids),
        )

        results = []
        for r in rows:
            entry = {
                "id": r["id"],
                "content": r["content"],
                "summary": r["summary"],
                "memory_type": r["memory_type"],
                "importance": r["importance"],
                "project": r["project"],
                "tags": r["tags"],
                "auto_tags": r["auto_tags"],
                "related_files": r["related_files"],
                "is_active": r["is_active"],
                "inactive_reason": r["inactive_reason"],
                "session_name": r["session_name"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
                "cluster": None,
            }
            if r["cluster_id"] is not None:
                entry["cluster"] = {
                    "id": r["cluster_id"],
                    "label": r["cluster_label"],
                    "size": r["cluster_size"],
                }
            results.append(entry)

        return results

    def modify(
        self,
        memory_id: int,
        action: str,
        content: str | None = None,
        memory_type: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
        reason: str | None = None,
    ) -> dict:
        """Update, inactivate, or reactivate a memory."""
        if action == "inactivate":
            self.db.execute(
                """
                UPDATE memories
                SET is_active = false, inactive_reason = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (reason or "No reason provided", memory_id),
            )
            self.db.commit()
            return {"id": memory_id, "action": "inactivated"}

        if action == "reactivate":
            self.db.execute(
                """
                UPDATE memories
                SET is_active = true, inactive_reason = NULL, updated_at = NOW()
                WHERE id = %s
                """,
                (memory_id,),
            )
            self.db.commit()
            return {"id": memory_id, "action": "reactivated"}

        if action == "update":
            updates = []
            params = []

            if content is not None:
                updates.append("content = %s")
                params.append(content)
                # Re-embed on content change
                vector = self.embedding.embed(content)
                updates.append("embedding = %s::vector")
                params.append(str(vector))

            if memory_type is not None:
                updates.append("memory_type = %s")
                params.append(memory_type)

            if importance is not None:
                updates.append("importance = %s")
                params.append(importance)

            if tags is not None:
                updates.append("tags = %s")
                params.append(tags)

            if not updates:
                return {"id": memory_id, "action": "no_changes"}

            updates.append("updated_at = NOW()")
            params.append(memory_id)

            self.db.execute(
                f"UPDATE memories SET {', '.join(updates)} WHERE id = %s",
                tuple(params),
            )
            self.db.commit()
            return {"id": memory_id, "action": "updated"}

        raise ValueError(f"Unknown action: {action}")

    def get_rules(
        self, project: str | None = None,
        limit: int | None = None, offset: int = 0,
    ) -> dict:
        """Retrieve active rule-type memories for a project and __global__.

        Returns dict with 'total', 'limit', 'offset', and 'items' keys.
        """
        project_param = project or "__global__"

        count_row = self.db.execute_one(
            """
            SELECT COUNT(*) as total FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE m.memory_type = 'rule' AND m.is_active = true
                AND (p.name = '__global__' OR p.name = %s)
            """,
            (project_param,),
        )
        total = count_row["total"]

        query = """
            SELECT m.id, m.content, m.importance, m.tags, m.created_at,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE m.memory_type = 'rule'
                AND m.is_active = true
                AND (p.name = '__global__' OR p.name = %s)
            ORDER BY m.importance DESC, m.created_at DESC
        """
        params: list = [project_param]

        if limit is not None:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])

        rows = self.db.execute(query, tuple(params))

        items = [
            {
                "id": r["id"],
                "content": r["content"],
                "importance": r["importance"],
                "project": r["project"],
                "tags": r["tags"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def export_project(self, project: str) -> list[dict]:
        """Export all active memories for a project."""
        rows = self.db.execute(
            """
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.related_files, m.session_name,
                   m.created_at, m.updated_at,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE p.name = %s AND m.is_active = true
            ORDER BY m.created_at DESC
            """,
            (project,),
        )

        return [
            {
                "id": r["id"],
                "content": r["content"],
                "summary": r["summary"],
                "memory_type": r["memory_type"],
                "importance": r["importance"],
                "project": r["project"],
                "tags": r["tags"],
                "auto_tags": r["auto_tags"],
                "related_files": r["related_files"],
                "session_name": r["session_name"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]
