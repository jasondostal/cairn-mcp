"""Work item management: hierarchical, graph-native work tracking.

Replaces flat tasks with epics/tasks/subtasks that participate in the
knowledge graph — linked to entities, memories, sessions, and decisions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.analytics import track_operation
from cairn.core.constants import (
    SHORT_ID_PREFIX,
    WorkItemStatus,
    WorkItemType,
)
from cairn.core.utils import get_or_create_project, get_project
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.embedding.interface import EmbeddingInterface
    from cairn.core.extraction import KnowledgeExtractor
    from cairn.graph.interface import GraphProvider

logger = logging.getLogger(__name__)


class WorkItemManager:
    """Handles work item lifecycle, hierarchy, dependencies, and graph sync."""

    def __init__(
        self,
        db: Database,
        embedding: EmbeddingInterface,
        graph: GraphProvider | None = None,
        knowledge_extractor: KnowledgeExtractor | None = None,
    ):
        self.db = db
        self.embedding = embedding
        self.graph = graph
        self.knowledge_extractor = knowledge_extractor

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_short_id(self, pg_id: int, parent_id: int | None = None) -> str:
        """Generate a hierarchical short ID.

        Root items: wi-{hex} (e.g. wi-002a)
        Children: parent_short_id.N (e.g. wi-002a.1, wi-002a.1.2)
        """
        if parent_id is None:
            return f"{SHORT_ID_PREFIX}{pg_id:04x}"

        parent = self.db.execute_one(
            "SELECT short_id FROM work_items WHERE id = %s", (parent_id,),
        )
        if not parent:
            return f"{SHORT_ID_PREFIX}{pg_id:04x}"

        # Find max existing child ordinal (survives deletions without collision)
        max_row = self.db.execute_one(
            """SELECT MAX(
                CAST(SPLIT_PART(short_id, '.', array_length(string_to_array(short_id, '.'), 1)) AS INTEGER)
            ) AS max_ord
            FROM work_items
            WHERE parent_id = %s AND short_id IS NOT NULL""",
            (parent_id,),
        )
        ordinal = (max_row["max_ord"] + 1) if max_row and max_row["max_ord"] is not None else 1
        return f"{parent['short_id']}.{ordinal}"

    def _embed_content(self, title: str, description: str | None) -> list[float] | None:
        """Generate embedding for title + description."""
        try:
            text = title
            if description:
                text = f"{title}\n{description[:500]}"
            return self.embedding.embed(text)
        except Exception:
            logger.warning("Failed to embed work item content", exc_info=True)
            return None

    def _graph_sync_work_item(
        self, pg_id: int, project_id: int, title: str, description: str | None,
        item_type: str, priority: int, status: str, short_id: str,
        content_embedding: list[float] | None = None,
        parent_id: int | None = None,
    ) -> None:
        """Dual-write: create WorkItem node in graph, update PG sync columns."""
        if not self.graph:
            return
        try:
            graph_uuid = self.graph.create_work_item(
                pg_id=pg_id, project_id=project_id, title=title,
                description=description, item_type=item_type,
                priority=priority, status=status, short_id=short_id,
                content_embedding=content_embedding,
            )
            self.db.execute(
                "UPDATE work_items SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                (graph_uuid, pg_id),
            )
            self.db.commit()

            # Add parent edge if applicable
            if parent_id:
                parent_row = self.db.execute_one(
                    "SELECT graph_uuid FROM work_items WHERE id = %s", (parent_id,),
                )
                if parent_row and parent_row["graph_uuid"]:
                    self.graph.add_work_item_parent_edge(
                        child_uuid=graph_uuid,
                        parent_uuid=parent_row["graph_uuid"],
                    )
        except Exception:
            logger.warning("Graph sync failed for work_item #%d", pg_id, exc_info=True)

    def _resolve_id(self, id_or_short_id: int | str) -> dict | None:
        """Resolve a work item by numeric ID or short_id string."""
        if isinstance(id_or_short_id, int) or (isinstance(id_or_short_id, str) and id_or_short_id.isdigit()):
            return self.db.execute_one(
                "SELECT * FROM work_items WHERE id = %s", (int(id_or_short_id),),
            )
        return self.db.execute_one(
            "SELECT * FROM work_items WHERE short_id = %s", (id_or_short_id,),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @track_operation("work_items.create")
    def create(
        self,
        project: str,
        title: str,
        description: str | None = None,
        item_type: str = "task",
        priority: int = 0,
        parent_id: int | None = None,
        session_name: str | None = None,
        metadata: dict | None = None,
        acceptance_criteria: str | None = None,
    ) -> dict:
        """Create a new work item."""
        if item_type not in WorkItemType.ALL:
            item_type = WorkItemType.TASK

        project_id = get_or_create_project(self.db, project)
        content_embedding = self._embed_content(title, description)

        row = self.db.execute_one(
            """
            INSERT INTO work_items
                (project_id, title, description, acceptance_criteria, item_type,
                 priority, parent_id, session_name, embedding, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id, created_at
            """,
            (
                project_id, title, description, acceptance_criteria, item_type,
                priority, parent_id, session_name,
                content_embedding, _json_dumps(metadata),
            ),
        )

        # Generate and set short_id
        short_id = self._generate_short_id(row["id"], parent_id)
        self.db.execute(
            "UPDATE work_items SET short_id = %s WHERE id = %s",
            (short_id, row["id"]),
        )
        self.db.commit()

        # Dual-write to graph
        self._graph_sync_work_item(
            pg_id=row["id"], project_id=project_id, title=title,
            description=description, item_type=item_type, priority=priority,
            status=WorkItemStatus.OPEN, short_id=short_id,
            content_embedding=content_embedding, parent_id=parent_id,
        )

        logger.info("Created work item %s (#%d) for project %s", short_id, row["id"], project)
        return {
            "id": row["id"],
            "short_id": short_id,
            "project": project,
            "title": title,
            "item_type": item_type,
            "priority": priority,
            "status": WorkItemStatus.OPEN,
            "parent_id": parent_id,
            "created_at": row["created_at"].isoformat(),
        }

    @track_operation("work_items.update")
    def update(self, id_or_short_id: int | str, **fields) -> dict:
        """Update work item fields. Validates status transitions."""
        item = self._resolve_id(id_or_short_id)
        if not item:
            raise ValueError(f"Work item {id_or_short_id} not found")

        # Status transition validation
        new_status = fields.get("status")
        if new_status is not None:
            if new_status not in WorkItemStatus.ALL:
                raise ValueError(f"Invalid status: {new_status}. Valid: {WorkItemStatus.ALL}")
        if new_status:
            current = item["status"]
            if current in WorkItemStatus.TERMINAL:
                raise ValueError(f"Cannot update terminal work item (status={current})")
            if new_status not in WorkItemStatus.TRANSITIONS.get(current, set()):
                raise ValueError(
                    f"Invalid transition: {current} → {new_status}. "
                    f"Valid: {WorkItemStatus.TRANSITIONS.get(current, set())}"
                )

        # Build dynamic SET clause
        allowed = {"title", "description", "acceptance_criteria", "priority",
                    "status", "assignee", "session_name", "metadata", "item_type"}
        sets = ["updated_at = NOW()"]
        params = []

        for key, val in fields.items():
            if key not in allowed:
                continue
            if key == "metadata":
                sets.append("metadata = metadata || %s::jsonb")
                params.append(_json_dumps(val))
            else:
                sets.append(f"{key} = %s")
                params.append(val)

        # Terminal state timestamps
        if new_status == WorkItemStatus.DONE:
            sets.append("completed_at = NOW()")
        elif new_status == WorkItemStatus.CANCELLED:
            sets.append("cancelled_at = NOW()")

        if len(sets) <= 1:
            return {"id": item["id"], "short_id": item["short_id"], "action": "no_changes"}

        params.append(item["id"])
        self.db.execute(
            f"UPDATE work_items SET {', '.join(sets)} WHERE id = %s",
            tuple(params),
        )

        # Re-embed if title or description changed
        if "title" in fields or "description" in fields:
            new_title = fields.get("title", item["title"])
            new_desc = fields.get("description", item["description"])
            emb = self._embed_content(new_title, new_desc)
            if emb:
                self.db.execute(
                    "UPDATE work_items SET embedding = %s WHERE id = %s",
                    (emb, item["id"]),
                )

        self.db.commit()

        # Graph status sync
        if new_status and self.graph and item.get("graph_uuid"):
            try:
                if new_status == WorkItemStatus.DONE:
                    self.graph.complete_work_item(item["graph_uuid"])
                else:
                    self.graph.update_work_item_status(item["graph_uuid"], new_status)
            except Exception:
                logger.warning("Graph status sync failed for work_item #%d", item["id"], exc_info=True)

        return {"id": item["id"], "short_id": item["short_id"], "action": "updated"}

    @track_operation("work_items.claim")
    def claim(self, work_item_id: int | str, assignee: str) -> dict:
        """Atomically claim a work item (open/ready → in_progress)."""
        item = self._resolve_id(work_item_id)
        if not item:
            raise ValueError(f"Work item {work_item_id} not found")

        row = self.db.execute_one(
            """
            UPDATE work_items
            SET status = 'in_progress', assignee = %s, claimed_at = NOW(), updated_at = NOW()
            WHERE id = %s AND status IN ('open', 'ready')
            RETURNING id, short_id
            """,
            (assignee, item["id"]),
        )
        if not row:
            raise ValueError(
                f"Cannot claim work item {item['short_id']} — "
                f"status is '{item['status']}' (must be open or ready)"
            )
        self.db.commit()

        # Graph sync
        if self.graph and item.get("graph_uuid"):
            try:
                self.graph.update_work_item_status(item["graph_uuid"], WorkItemStatus.IN_PROGRESS)
                self.graph.assign_work_item(item["graph_uuid"], assignee)
            except Exception:
                logger.warning("Graph claim sync failed for work_item #%d", item["id"], exc_info=True)

        return {
            "id": row["id"],
            "short_id": row["short_id"],
            "assignee": assignee,
            "status": WorkItemStatus.IN_PROGRESS,
            "action": "claimed",
        }

    @track_operation("work_items.complete")
    def complete(self, work_item_id: int | str) -> dict:
        """Mark a work item as done and auto-unblock dependents."""
        item = self._resolve_id(work_item_id)
        if not item:
            raise ValueError(f"Work item {work_item_id} not found")

        if item["status"] in WorkItemStatus.TERMINAL:
            raise ValueError(f"Work item {item['short_id']} is already {item['status']}")

        self.db.execute(
            """
            UPDATE work_items
            SET status = 'done', completed_at = NOW(), updated_at = NOW()
            WHERE id = %s
            """,
            (item["id"],),
        )

        # Auto-unblock: items that were blocked only by this item
        blocked_rows = self.db.execute(
            """
            SELECT wb.blocked_id
            FROM work_item_blocks wb
            WHERE wb.blocker_id = %s
            """,
            (item["id"],),
        )
        for br in blocked_rows:
            # Check if the blocked item has any remaining active blockers
            remaining = self.db.execute_one(
                """
                SELECT COUNT(*) AS cnt FROM work_item_blocks wb
                JOIN work_items wi ON wi.id = wb.blocker_id
                WHERE wb.blocked_id = %s AND wb.blocker_id != %s
                  AND wi.status NOT IN ('done', 'cancelled')
                """,
                (br["blocked_id"], item["id"]),
            )
            if remaining and remaining["cnt"] == 0:
                # No more active blockers — flip BLOCKED → OPEN
                self.db.execute(
                    """
                    UPDATE work_items SET status = 'open', updated_at = NOW()
                    WHERE id = %s AND status = 'blocked'
                    """,
                    (br["blocked_id"],),
                )

        self.db.commit()

        # Graph sync
        if self.graph and item.get("graph_uuid"):
            try:
                self.graph.complete_work_item(item["graph_uuid"])
            except Exception:
                logger.warning("Graph complete failed for work_item #%d", item["id"], exc_info=True)

        return {"id": item["id"], "short_id": item["short_id"], "action": "completed"}

    @track_operation("work_items.add_child")
    def add_child(
        self,
        parent_id: int | str,
        title: str,
        description: str | None = None,
        priority: int = 0,
        **kwargs,
    ) -> dict:
        """Add a child work item. Auto-infers item_type from parent."""
        parent = self._resolve_id(parent_id)
        if not parent:
            raise ValueError(f"Parent work item {parent_id} not found")

        # Get project name
        proj_row = self.db.execute_one(
            "SELECT name FROM projects WHERE id = %s", (parent["project_id"],),
        )
        project_name = proj_row["name"] if proj_row else "unknown"

        child_type = WorkItemType.CHILD_TYPE.get(parent["item_type"], WorkItemType.SUBTASK)

        return self.create(
            project=project_name,
            title=title,
            description=description,
            item_type=child_type,
            priority=priority,
            parent_id=parent["id"],
            **kwargs,
        )

    @track_operation("work_items.block")
    def block(self, blocker_id: int | str, blocked_id: int | str) -> dict:
        """Add a dependency: blocker must complete before blocked can proceed."""
        blocker = self._resolve_id(blocker_id)
        blocked = self._resolve_id(blocked_id)
        if not blocker:
            raise ValueError(f"Blocker work item {blocker_id} not found")
        if not blocked:
            raise ValueError(f"Blocked work item {blocked_id} not found")
        if blocker["id"] == blocked["id"]:
            raise ValueError("A work item cannot block itself")

        self.db.execute(
            """
            INSERT INTO work_item_blocks (blocker_id, blocked_id)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
            """,
            (blocker["id"], blocked["id"]),
        )

        # Set blocked item status to BLOCKED if it's not already terminal
        if blocked["status"] not in WorkItemStatus.TERMINAL:
            self.db.execute(
                "UPDATE work_items SET status = 'blocked', updated_at = NOW() WHERE id = %s",
                (blocked["id"],),
            )

        self.db.commit()

        # Graph sync
        if self.graph:
            try:
                if blocker.get("graph_uuid") and blocked.get("graph_uuid"):
                    self.graph.add_work_item_blocks_edge(
                        blocker["graph_uuid"], blocked["graph_uuid"],
                    )
            except Exception:
                logger.warning("Graph block sync failed", exc_info=True)

        return {
            "blocker": {"id": blocker["id"], "short_id": blocker["short_id"]},
            "blocked": {"id": blocked["id"], "short_id": blocked["short_id"]},
            "action": "blocked",
        }

    @track_operation("work_items.unblock")
    def unblock(self, blocker_id: int | str, blocked_id: int | str) -> dict:
        """Remove a dependency edge."""
        blocker = self._resolve_id(blocker_id)
        blocked = self._resolve_id(blocked_id)
        if not blocker:
            raise ValueError(f"Blocker work item {blocker_id} not found")
        if not blocked:
            raise ValueError(f"Blocked work item {blocked_id} not found")

        self.db.execute(
            "DELETE FROM work_item_blocks WHERE blocker_id = %s AND blocked_id = %s",
            (blocker["id"], blocked["id"]),
        )

        # Check remaining blockers — if none, flip BLOCKED → OPEN
        remaining = self.db.execute_one(
            """
            SELECT COUNT(*) AS cnt FROM work_item_blocks wb
            JOIN work_items wi ON wi.id = wb.blocker_id
            WHERE wb.blocked_id = %s AND wi.status NOT IN ('done', 'cancelled')
            """,
            (blocked["id"],),
        )
        if remaining and remaining["cnt"] == 0 and blocked["status"] == WorkItemStatus.BLOCKED:
            self.db.execute(
                "UPDATE work_items SET status = 'open', updated_at = NOW() WHERE id = %s",
                (blocked["id"],),
            )

        self.db.commit()

        # Graph sync
        if self.graph:
            try:
                if blocker.get("graph_uuid") and blocked.get("graph_uuid"):
                    self.graph.remove_work_item_blocks_edge(
                        blocker["graph_uuid"], blocked["graph_uuid"],
                    )
            except Exception:
                logger.warning("Graph unblock sync failed", exc_info=True)

        return {
            "blocker": {"id": blocker["id"], "short_id": blocker["short_id"]},
            "blocked": {"id": blocked["id"], "short_id": blocked["short_id"]},
            "action": "unblocked",
        }

    @track_operation("work_items.list")
    def list_items(
        self,
        project: str | None = None,
        status: str | None = None,
        item_type: str | None = None,
        assignee: str | None = None,
        parent_id: int | None = None,
        include_children: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Filtered paginated list of work items."""
        conditions = ["TRUE"]
        params: list = []

        if project:
            project_id = get_project(self.db, project)
            if project_id is None:
                return {"total": 0, "limit": limit, "offset": offset, "items": []}
            conditions.append("wi.project_id = %s")
            params.append(project_id)

        if status:
            conditions.append("wi.status = %s")
            params.append(status)

        if item_type:
            conditions.append("wi.item_type = %s")
            params.append(item_type)

        if assignee:
            conditions.append("wi.assignee = %s")
            params.append(assignee)

        if parent_id is not None:
            if include_children:
                # Separate query for recursive subtree (CTE can't nest in IN(...))
                subtree_rows = self.db.execute(
                    """
                    WITH RECURSIVE subtree AS (
                        SELECT id FROM work_items WHERE id = %s
                        UNION ALL
                        SELECT c.id FROM work_items c
                        JOIN subtree s ON c.parent_id = s.id
                    )
                    SELECT id FROM subtree
                    """,
                    (parent_id,),
                )
                subtree_ids = [r["id"] for r in subtree_rows]
                if not subtree_ids:
                    return {"total": 0, "limit": limit, "offset": offset, "items": []}
                placeholders = ", ".join(["%s"] * len(subtree_ids))
                conditions.append(f"wi.id IN ({placeholders})")
                params.extend(subtree_ids)
            else:
                conditions.append("wi.parent_id = %s")
                params.append(parent_id)

        where = " AND ".join(conditions)

        count_row = self.db.execute_one(
            f"SELECT COUNT(*) AS total FROM work_items wi WHERE {where}",
            tuple(params),
        )
        total = count_row["total"]

        query = f"""
            SELECT wi.id, wi.short_id, wi.title, wi.item_type, wi.priority,
                   wi.status, wi.assignee, wi.parent_id, wi.session_name,
                   wi.created_at, wi.updated_at, wi.completed_at, wi.cancelled_at,
                   p.name AS project,
                   (SELECT COUNT(*) FROM work_items c WHERE c.parent_id = wi.id) AS children_count
            FROM work_items wi
            LEFT JOIN projects p ON wi.project_id = p.id
            WHERE {where}
            ORDER BY wi.priority DESC, wi.created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        rows = self.db.execute(query, tuple(params))

        items = [
            {
                "id": r["id"],
                "short_id": r["short_id"],
                "title": r["title"],
                "item_type": r["item_type"],
                "priority": r["priority"],
                "status": r["status"],
                "assignee": r["assignee"],
                "parent_id": r["parent_id"],
                "project": r["project"],
                "children_count": r["children_count"],
                "session_name": r["session_name"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    @track_operation("work_items.ready_queue")
    def ready_queue(self, project: str, limit: int = 10) -> dict:
        """Unblocked, unassigned work items ordered by priority.

        Tries Neo4j first, falls back to Postgres.
        """
        project_id = get_project(self.db, project)
        if project_id is None:
            return {"project": project, "items": []}

        # Try graph-based ready queue
        if self.graph:
            try:
                items = self.graph.work_item_ready_queue(project_id, limit)
                if items is not None:
                    return {"project": project, "items": items, "source": "graph"}
            except Exception:
                logger.debug("Graph ready_queue failed, using Postgres fallback", exc_info=True)

        # Postgres fallback
        rows = self.db.execute(
            """
            SELECT wi.id, wi.title, wi.priority, wi.short_id, wi.item_type
            FROM work_items wi
            WHERE wi.project_id = %s
              AND wi.status IN ('open', 'ready')
              AND wi.assignee IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM work_item_blocks wb
                JOIN work_items blocker ON blocker.id = wb.blocker_id
                WHERE wb.blocked_id = wi.id
                  AND blocker.status NOT IN ('done', 'cancelled')
              )
            ORDER BY wi.priority DESC, wi.created_at ASC
            LIMIT %s
            """,
            (project_id, limit),
        )
        return {
            "project": project,
            "items": [dict(r) for r in rows],
            "source": "postgres",
        }

    @track_operation("work_items.get")
    def get(self, id_or_short_id: int | str) -> dict:
        """Full detail for a single work item."""
        item = self._resolve_id(id_or_short_id)
        if not item:
            raise ValueError(f"Work item {id_or_short_id} not found")

        # Project name
        proj = self.db.execute_one(
            "SELECT name FROM projects WHERE id = %s", (item["project_id"],),
        )

        # Parent info
        parent_info = None
        if item["parent_id"]:
            parent = self.db.execute_one(
                "SELECT id, short_id, title FROM work_items WHERE id = %s",
                (item["parent_id"],),
            )
            if parent:
                parent_info = {"id": parent["id"], "short_id": parent["short_id"], "title": parent["title"]}

        # Children count
        children = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM work_items WHERE parent_id = %s",
            (item["id"],),
        )

        # Blockers
        blockers = self.db.execute(
            """
            SELECT wi.id, wi.short_id, wi.title, wi.status
            FROM work_item_blocks wb
            JOIN work_items wi ON wi.id = wb.blocker_id
            WHERE wb.blocked_id = %s
            """,
            (item["id"],),
        )

        # Blocking (items this blocks)
        blocking = self.db.execute(
            """
            SELECT wi.id, wi.short_id, wi.title, wi.status
            FROM work_item_blocks wb
            JOIN work_items wi ON wi.id = wb.blocked_id
            WHERE wb.blocker_id = %s
            """,
            (item["id"],),
        )

        # Linked memories
        linked = self.db.execute(
            """
            SELECT m.id, m.summary, m.memory_type
            FROM work_item_memory_links wml
            JOIN memories m ON m.id = wml.memory_id
            WHERE wml.work_item_id = %s
            """,
            (item["id"],),
        )

        return {
            "id": item["id"],
            "short_id": item["short_id"],
            "project": proj["name"] if proj else None,
            "title": item["title"],
            "description": item["description"],
            "acceptance_criteria": item["acceptance_criteria"],
            "item_type": item["item_type"],
            "priority": item["priority"],
            "status": item["status"],
            "assignee": item["assignee"],
            "parent": parent_info,
            "children_count": children["cnt"] if children else 0,
            "blockers": [dict(b) for b in blockers],
            "blocking": [dict(b) for b in blocking],
            "linked_memories": [dict(m) for m in linked],
            "metadata": item["metadata"],
            "session_name": item["session_name"],
            "created_at": item["created_at"].isoformat() if item["created_at"] else None,
            "updated_at": item["updated_at"].isoformat() if item["updated_at"] else None,
            "completed_at": item["completed_at"].isoformat() if item["completed_at"] else None,
            "cancelled_at": item["cancelled_at"].isoformat() if item["cancelled_at"] else None,
        }

    @track_operation("work_items.link_memories")
    def link_memories(self, work_item_id: int | str, memory_ids: list[int]) -> dict:
        """Link memories to a work item."""
        item = self._resolve_id(work_item_id)
        if not item:
            raise ValueError(f"Work item {work_item_id} not found")

        for mid in memory_ids:
            self.db.execute(
                """
                INSERT INTO work_item_memory_links (work_item_id, memory_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (item["id"], mid),
            )
        self.db.commit()

        # Graph sync
        if self.graph and item.get("graph_uuid"):
            for mid in memory_ids:
                try:
                    self.graph.link_work_item_to_memory(item["graph_uuid"], mid)
                except Exception:
                    logger.debug("Graph link failed for work_item #%d -> memory #%d", item["id"], mid)

        return {
            "work_item_id": item["id"],
            "short_id": item["short_id"],
            "linked": memory_ids,
        }


def _json_dumps(data: dict | None) -> str:
    """Serialize dict to JSON string for Postgres JSONB."""
    import json
    return json.dumps(data or {})
