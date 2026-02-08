"""Project management: docs, linking, listing."""

from __future__ import annotations

import logging

from cairn.storage.database import Database

logger = logging.getLogger(__name__)

VALID_DOC_TYPES = ["brief", "prd", "plan"]
VALID_LINK_TYPES = ["related", "parent", "child", "dependency", "fork", "template"]


class ProjectManager:
    """Handles project documents and relationships."""

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

    def list_all(self, limit: int | None = None, offset: int = 0) -> dict:
        """List all projects with memory counts and optional pagination.

        Returns dict with 'total', 'limit', 'offset', and 'items' keys.
        """
        count_row = self.db.execute_one("SELECT COUNT(*) as total FROM projects")
        total = count_row["total"]

        query = """
            SELECT p.id, p.name, p.created_at,
                   COUNT(m.id) FILTER (WHERE m.is_active = true) as memory_count
            FROM projects p
            LEFT JOIN memories m ON m.project_id = p.id
            GROUP BY p.id, p.name, p.created_at
            ORDER BY memory_count DESC, p.name
        """
        params: list = []

        if limit is not None:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])

        rows = self.db.execute(query, tuple(params) if params else None)

        items = [
            {
                "id": r["id"],
                "name": r["name"],
                "memory_count": r["memory_count"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def create_doc(self, project: str, doc_type: str, content: str) -> dict:
        """Create a project document (brief, PRD, or plan)."""
        if doc_type not in VALID_DOC_TYPES:
            raise ValueError(f"Invalid doc_type: {doc_type}. Must be one of: {VALID_DOC_TYPES}")

        project_id = self._resolve_project_id(project)
        row = self.db.execute_one(
            """
            INSERT INTO project_documents (project_id, doc_type, content)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (project_id, doc_type, content),
        )
        self.db.commit()

        logger.info("Created %s doc for project %s (id=%d)", doc_type, project, row["id"])
        return {
            "id": row["id"],
            "project": project,
            "doc_type": doc_type,
            "created_at": row["created_at"].isoformat(),
        }

    def get_docs(self, project: str, doc_type: str | None = None) -> list[dict]:
        """Get documents for a project, optionally filtered by type."""
        project_id = self._resolve_project_id(project)

        if doc_type:
            rows = self.db.execute(
                """
                SELECT id, doc_type, content, created_at, updated_at
                FROM project_documents
                WHERE project_id = %s AND doc_type = %s
                ORDER BY created_at DESC
                """,
                (project_id, doc_type),
            )
        else:
            rows = self.db.execute(
                """
                SELECT id, doc_type, content, created_at, updated_at
                FROM project_documents
                WHERE project_id = %s
                ORDER BY doc_type, created_at DESC
                """,
                (project_id,),
            )

        return [
            {
                "id": r["id"],
                "project": project,
                "doc_type": r["doc_type"],
                "content": r["content"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]

    def update_doc(self, doc_id: int, content: str) -> dict:
        """Update a project document's content."""
        self.db.execute(
            "UPDATE project_documents SET content = %s, updated_at = NOW() WHERE id = %s",
            (content, doc_id),
        )
        self.db.commit()
        return {"id": doc_id, "action": "updated"}

    def link(self, source: str, target: str, link_type: str = "related") -> dict:
        """Link two projects."""
        if link_type not in VALID_LINK_TYPES:
            raise ValueError(f"Invalid link_type: {link_type}. Must be one of: {VALID_LINK_TYPES}")

        source_id = self._resolve_project_id(source)
        target_id = self._resolve_project_id(target)

        self.db.execute(
            """
            INSERT INTO project_links (source_id, target_id, link_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (source_id, target_id) DO UPDATE SET link_type = EXCLUDED.link_type
            """,
            (source_id, target_id, link_type),
        )
        self.db.commit()
        return {"source": source, "target": target, "link_type": link_type}

    def get_links(self, project: str) -> list[dict]:
        """Get all links for a project (both directions)."""
        project_id = self._resolve_project_id(project)

        rows = self.db.execute(
            """
            SELECT pl.link_type, pl.created_at,
                   ps.name as source, pt.name as target
            FROM project_links pl
            JOIN projects ps ON pl.source_id = ps.id
            JOIN projects pt ON pl.target_id = pt.id
            WHERE pl.source_id = %s OR pl.target_id = %s
            ORDER BY pl.created_at DESC
            """,
            (project_id, project_id),
        )

        return [
            {
                "source": r["source"],
                "target": r["target"],
                "link_type": r["link_type"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
