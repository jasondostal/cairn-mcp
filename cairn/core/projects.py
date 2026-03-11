"""Project management: docs, linking, listing."""

from __future__ import annotations

import logging

from cairn.core.analytics import track_operation
from cairn.core.constants import (
    MAX_PREFIX_LENGTH,
    MIN_PREFIX_LENGTH,
    VALID_DOC_TYPES,
    VALID_LINK_TYPES,
)
from cairn.core.utils import get_or_create_project, get_project
from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class ProjectManager:
    """Handles project documents and relationships."""

    def __init__(self, db: Database):
        self.db = db

    @track_operation("projects.list")
    def list_all(self, limit: int | None = None, offset: int = 0) -> dict:
        """List all projects with memory counts and optional pagination.

        Returns dict with 'total', 'limit', 'offset', and 'items' keys.
        """
        count_row = self.db.execute_one("SELECT COUNT(*) as total FROM projects")
        assert count_row is not None
        total = count_row["total"]

        query = """
            SELECT p.id, p.name, p.work_item_prefix, p.created_at,
                   COALESCE(mc.cnt, 0) AS memory_count,
                   COALESCE(dc.cnt, 0) AS doc_count,
                   COALESCE(wc.cnt, 0) AS work_item_count,
                   GREATEST(mc.latest, dc.latest, wc.latest) AS last_activity
            FROM projects p
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt, MAX(updated_at) AS latest
                FROM memories WHERE project_id = p.id AND is_active = true
            ) mc ON true
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt, MAX(updated_at) AS latest
                FROM project_documents WHERE project_id = p.id
            ) dc ON true
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt, MAX(updated_at) AS latest
                FROM work_items WHERE project_id = p.id
            ) wc ON true
            ORDER BY last_activity DESC NULLS LAST, p.name
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
                "work_item_prefix": r["work_item_prefix"],
                "memory_count": r["memory_count"],
                "doc_count": r["doc_count"],
                "work_item_count": r["work_item_count"],
                "last_activity": r["last_activity"].isoformat() if r["last_activity"] else None,
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    @track_operation("projects.update_prefix")
    def update_prefix(self, project: str, new_prefix: str) -> dict:
        """Update a project's work_item_prefix with collision check."""
        new_prefix = new_prefix.strip().lower()
        if not new_prefix:
            raise ValueError("prefix cannot be empty")
        if len(new_prefix) < MIN_PREFIX_LENGTH or len(new_prefix) > MAX_PREFIX_LENGTH:
            raise ValueError(
                f"prefix must be between {MIN_PREFIX_LENGTH} and {MAX_PREFIX_LENGTH} characters"
            )
        if not new_prefix.isalnum():
            raise ValueError("prefix must be alphanumeric")

        project_id = get_project(self.db, project)
        if project_id is None:
            raise ValueError(f"project not found: {project}")

        # Check for collision
        collision = self.db.execute_one(
            "SELECT name FROM projects WHERE work_item_prefix = %s AND id != %s",
            (new_prefix, project_id),
        )
        if collision:
            raise ValueError(
                f"prefix '{new_prefix}' is already used by project '{collision['name']}'"
            )

        self.db.execute(
            "UPDATE projects SET work_item_prefix = %s WHERE id = %s",
            (new_prefix, project_id),
        )
        self.db.commit()
        logger.info("Updated prefix for project %s to '%s'", project, new_prefix)
        return {"project": project, "work_item_prefix": new_prefix}

    @track_operation("projects.create_doc")
    def create_doc(self, project: str, doc_type: str, content: str, title: str | None = None) -> dict:
        """Create a project document."""
        if doc_type not in VALID_DOC_TYPES:
            raise ValueError(f"Invalid doc_type: {doc_type}. Must be one of: {VALID_DOC_TYPES}")

        project_id = get_or_create_project(self.db, project)
        row = self.db.execute_one(
            """
            INSERT INTO project_documents (project_id, doc_type, content, title)
            VALUES (%s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (project_id, doc_type, content, title),
        )
        assert row is not None
        self.db.commit()

        logger.info("Created %s doc for project %s (id=%d)", doc_type, project, row["id"])
        return {
            "id": row["id"],
            "project": project,
            "doc_type": doc_type,
            "title": title,
            "created_at": row["created_at"].isoformat(),
        }

    @track_operation("projects.get_docs")
    def get_docs(self, project: str, doc_type: str | None = None) -> list[dict]:
        """Get documents for a project, optionally filtered by type."""
        project_id = get_project(self.db, project)
        if project_id is None:
            return []

        if doc_type:
            rows = self.db.execute(
                """
                SELECT id, doc_type, title, content, created_at, updated_at
                FROM project_documents
                WHERE project_id = %s AND doc_type = %s
                ORDER BY created_at DESC
                """,
                (project_id, doc_type),
            )
        else:
            rows = self.db.execute(
                """
                SELECT id, doc_type, title, content, created_at, updated_at
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
                "title": r["title"],
                "content": r["content"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]

    def list_all_docs(
        self,
        project: str | list[str] | None = None,
        doc_type: str | list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict:
        """List docs across all projects with optional filters and pagination."""
        where = []
        params: list = []

        if project:
            if isinstance(project, list):
                where.append("p.name = ANY(%s)")
                params.append(project)
            else:
                where.append("p.name = %s")
                params.append(project)
        if doc_type:
            if isinstance(doc_type, list):
                where.append("d.doc_type = ANY(%s)")
                params.append(doc_type)
            else:
                where.append("d.doc_type = %s")
                params.append(doc_type)

        where_clause = (" WHERE " + " AND ".join(where)) if where else ""

        count_row = self.db.execute_one(
            f"""
            SELECT COUNT(*) as total
            FROM project_documents d
            JOIN projects p ON d.project_id = p.id
            {where_clause}
            """,
            tuple(params) if params else None,
        )
        assert count_row is not None
        total = count_row["total"]

        query = f"""
            SELECT d.id, d.doc_type, d.title, d.content, d.created_at, d.updated_at,
                   p.name as project
            FROM project_documents d
            JOIN projects p ON d.project_id = p.id
            {where_clause}
            ORDER BY d.updated_at DESC
        """
        query_params = list(params)
        if limit is not None:
            query += " LIMIT %s OFFSET %s"
            query_params.extend([limit, offset])

        rows = self.db.execute(query, tuple(query_params) if query_params else None)

        items = [
            {
                "id": r["id"],
                "project": r["project"],
                "doc_type": r["doc_type"],
                "title": r["title"],
                "content": r["content"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def get_doc(self, doc_id: int) -> dict | None:
        """Get a single document by ID with project name."""
        row = self.db.execute_one(
            """
            SELECT d.id, d.doc_type, d.title, d.content, d.created_at, d.updated_at,
                   p.name as project
            FROM project_documents d
            JOIN projects p ON d.project_id = p.id
            WHERE d.id = %s
            """,
            (doc_id,),
        )
        if row is None:
            return None
        return {
            "id": row["id"],
            "project": row["project"],
            "doc_type": row["doc_type"],
            "title": row["title"],
            "content": row["content"],
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }

    @track_operation("projects.update_doc")
    def update_doc(self, doc_id: int, content: str, title: str | None = None) -> dict:
        """Update a project document's content and optionally its title."""
        if title is not None:
            self.db.execute(
                "UPDATE project_documents SET content = %s, title = %s, updated_at = NOW() WHERE id = %s",
                (content, title, doc_id),
            )
        else:
            self.db.execute(
                "UPDATE project_documents SET content = %s, updated_at = NOW() WHERE id = %s",
                (content, doc_id),
            )
        self.db.commit()
        return {"id": doc_id, "action": "updated"}

    @track_operation("projects.link")
    def link(self, source: str, target: str, link_type: str = "related") -> dict:
        """Link two projects."""
        if link_type not in VALID_LINK_TYPES:
            raise ValueError(f"Invalid link_type: {link_type}. Must be one of: {VALID_LINK_TYPES}")

        source_id = get_or_create_project(self.db,source)
        target_id = get_or_create_project(self.db,target)

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

    @track_operation("projects.upload_attachment")
    def upload_attachment(
        self, doc_id: int, filename: str, mime_type: str, data: bytes,
    ) -> dict:
        """Upload an attachment to a document."""
        from cairn.core.constants import ALLOWED_ATTACHMENT_TYPES, MAX_ATTACHMENT_SIZE

        # Verify doc exists
        doc = self.get_doc(doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")

        if mime_type not in ALLOWED_ATTACHMENT_TYPES:
            raise ValueError(
                f"Unsupported file type: {mime_type}. "
                f"Allowed: {', '.join(sorted(ALLOWED_ATTACHMENT_TYPES))}"
            )

        size = len(data)
        if size > MAX_ATTACHMENT_SIZE:
            raise ValueError(
                f"File too large: {size} bytes (max {MAX_ATTACHMENT_SIZE})"
            )

        row = self.db.execute_one(
            """
            INSERT INTO document_attachments (document_id, filename, mime_type, size_bytes, data)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (doc_id, filename, mime_type, size, data),
        )
        assert row is not None
        self.db.commit()

        logger.info(
            "Uploaded attachment %s for doc %d (%s, %d bytes)",
            filename, doc_id, mime_type, size,
        )
        return {
            "id": row["id"],
            "document_id": doc_id,
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": size,
            "url": f"cairn://attachments/{row['id']}/{filename}",
            "created_at": row["created_at"].isoformat(),
        }

    @track_operation("projects.get_attachment")
    def get_attachment(self, attachment_id: int) -> dict | None:
        """Get a single attachment including binary data."""
        row = self.db.execute_one(
            """
            SELECT id, document_id, filename, mime_type, size_bytes, data, created_at
            FROM document_attachments WHERE id = %s
            """,
            (attachment_id,),
        )
        if row is None:
            return None
        return {
            "id": row["id"],
            "document_id": row["document_id"],
            "filename": row["filename"],
            "mime_type": row["mime_type"],
            "size_bytes": row["size_bytes"],
            "data": bytes(row["data"]),
            "created_at": row["created_at"].isoformat(),
        }

    @track_operation("projects.list_attachments")
    def list_attachments(self, doc_id: int) -> list[dict]:
        """List attachments for a document (metadata only, no binary data)."""
        rows = self.db.execute(
            """
            SELECT id, document_id, filename, mime_type, size_bytes, created_at
            FROM document_attachments WHERE document_id = %s
            ORDER BY created_at
            """,
            (doc_id,),
        )
        return [
            {
                "id": r["id"],
                "document_id": r["document_id"],
                "filename": r["filename"],
                "mime_type": r["mime_type"],
                "size_bytes": r["size_bytes"],
                "url": f"cairn://attachments/{r['id']}/{r['filename']}",
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]

    @track_operation("projects.delete_attachment")
    def delete_attachment(self, attachment_id: int) -> dict:
        """Delete a single attachment."""
        self.db.execute(
            "DELETE FROM document_attachments WHERE id = %s", (attachment_id,),
        )
        self.db.commit()
        return {"id": attachment_id, "action": "deleted"}

    @track_operation("projects.get_links")
    def get_links(self, project: str) -> list[dict]:
        """Get all links for a project (both directions)."""
        project_id = get_project(self.db, project)
        if project_id is None:
            return []

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
