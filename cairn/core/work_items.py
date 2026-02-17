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
    ActivityType,
    AgentState,
    GateType,
    RiskTier,
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
        risk_tier: int = 0,
        gate_type: str | None = None,
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
                risk_tier=risk_tier, gate_type=gate_type,
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

    def _log_activity(
        self,
        work_item_id: int,
        actor: str | None,
        activity_type: str,
        content: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record an activity entry for a work item."""
        self.db.execute(
            """INSERT INTO work_item_activity (work_item_id, actor, activity_type, content, metadata)
               VALUES (%s, %s, %s, %s, %s::jsonb)""",
            (work_item_id, actor, activity_type, content, _json_dumps(metadata)),
        )

    def _collect_constraints(self, item: dict) -> dict:
        """Walk up the parent chain collecting merged constraints."""
        merged = dict(item.get("constraints") or {})
        parent_id = item.get("parent_id")
        seen = {item["id"]}
        while parent_id and parent_id not in seen:
            seen.add(parent_id)
            parent = self.db.execute_one(
                "SELECT id, parent_id, constraints FROM work_items WHERE id = %s",
                (parent_id,),
            )
            if not parent:
                break
            parent_constraints = parent.get("constraints") or {}
            # Parent constraints are defaults; child overrides take precedence
            merged = {**parent_constraints, **merged}
            parent_id = parent.get("parent_id")
        return merged

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
        constraints: dict | None = None,
        risk_tier: int | None = None,
    ) -> dict:
        """Create a new work item."""
        if item_type not in WorkItemType.ALL:
            item_type = WorkItemType.TASK

        if risk_tier is not None and risk_tier not in RiskTier.ALL:
            risk_tier = RiskTier.PATROL

        project_id = get_or_create_project(self.db, project)
        content_embedding = self._embed_content(title, description)

        row = self.db.execute_one(
            """
            INSERT INTO work_items
                (project_id, title, description, acceptance_criteria, item_type,
                 priority, parent_id, session_name, embedding, metadata,
                 constraints, risk_tier)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            RETURNING id, created_at
            """,
            (
                project_id, title, description, acceptance_criteria, item_type,
                priority, parent_id, session_name,
                content_embedding, _json_dumps(metadata),
                _json_dumps(constraints), risk_tier or 0,
            ),
        )

        # Generate and set short_id
        short_id = self._generate_short_id(row["id"], parent_id)
        self.db.execute(
            "UPDATE work_items SET short_id = %s WHERE id = %s",
            (short_id, row["id"]),
        )

        # Log creation activity
        self._log_activity(
            row["id"], None, ActivityType.CREATED,
            f"Created {item_type}: {title}",
            {"item_type": item_type, "priority": priority, "risk_tier": risk_tier or 0},
        )

        self.db.commit()

        # Risk tier CRITICAL auto-gates with human gate
        if risk_tier == RiskTier.CRITICAL:
            self.set_gate(
                row["id"], GateType.HUMAN,
                gate_data={"question": "This is a CRITICAL risk item. Confirm before proceeding.", "auto_set": True},
            )

        # Dual-write to graph
        self._graph_sync_work_item(
            pg_id=row["id"], project_id=project_id, title=title,
            description=description, item_type=item_type, priority=priority,
            status=WorkItemStatus.OPEN, short_id=short_id,
            content_embedding=content_embedding, parent_id=parent_id,
            risk_tier=risk_tier or 0,
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
            "risk_tier": risk_tier or 0,
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
                    "status", "assignee", "session_name", "metadata", "item_type",
                    "risk_tier", "constraints"}
        sets = ["updated_at = NOW()"]
        params = []

        for key, val in fields.items():
            if key not in allowed:
                continue
            if key == "metadata":
                sets.append("metadata = metadata || %s::jsonb")
                params.append(_json_dumps(val))
            elif key == "constraints":
                sets.append("constraints = constraints || %s::jsonb")
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

        # Log status change activity
        if new_status:
            self._log_activity(
                item["id"], None, ActivityType.STATUS_CHANGE,
                f"Status: {item['status']} -> {new_status}",
                {"old_status": item["status"], "new_status": new_status},
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

        # Graph risk_tier sync
        if "risk_tier" in fields and self.graph and item.get("graph_uuid"):
            try:
                self.graph.update_work_item_risk_tier(item["graph_uuid"], fields["risk_tier"])
            except Exception:
                logger.debug("Graph risk_tier sync failed for work_item #%d", item["id"])

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

        self._log_activity(
            item["id"], assignee, ActivityType.CLAIM,
            f"Claimed by {assignee}",
            {"assignee": assignee, "old_status": item["status"]},
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

        self._log_activity(
            item["id"], None, ActivityType.STATUS_CHANGE,
            f"Completed (was {item['status']})",
            {"old_status": item["status"], "new_status": "done"},
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
        """Add a child work item. Auto-infers item_type from parent.

        Inherits parent constraints (merged with any child overrides) and
        risk_tier (if child doesn't specify one).
        """
        parent = self._resolve_id(parent_id)
        if not parent:
            raise ValueError(f"Parent work item {parent_id} not found")

        # Get project name
        proj_row = self.db.execute_one(
            "SELECT name FROM projects WHERE id = %s", (parent["project_id"],),
        )
        project_name = proj_row["name"] if proj_row else "unknown"

        child_type = WorkItemType.CHILD_TYPE.get(parent["item_type"], WorkItemType.SUBTASK)

        # Cascade constraints: parent + child overrides
        parent_constraints = parent.get("constraints") or {}
        child_constraints = {**parent_constraints, **(kwargs.pop("constraints", None) or {})}

        # Inherit risk_tier if child doesn't specify one
        if "risk_tier" not in kwargs or kwargs.get("risk_tier") is None:
            kwargs["risk_tier"] = parent.get("risk_tier") or 0

        return self.create(
            project=project_name,
            title=title,
            description=description,
            item_type=child_type,
            priority=priority,
            parent_id=parent["id"],
            constraints=child_constraints,
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
                   wi.risk_tier, wi.gate_type, wi.agent_state,
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
                "risk_tier": r["risk_tier"] or 0,
                "gate_type": r["gate_type"],
                "agent_state": r["agent_state"],
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
            "risk_tier": item.get("risk_tier") or 0,
            "gate_type": item.get("gate_type"),
            "gate_data": item.get("gate_data") or {},
            "gate_resolved_at": item["gate_resolved_at"].isoformat() if item.get("gate_resolved_at") else None,
            "gate_response": item.get("gate_response"),
            "constraints": item.get("constraints") or {},
            "agent_state": item.get("agent_state"),
            "last_heartbeat": item["last_heartbeat"].isoformat() if item.get("last_heartbeat") else None,
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


    # ------------------------------------------------------------------
    # Gate primitives (v0.48.0)
    # ------------------------------------------------------------------

    @track_operation("work_items.set_gate")
    def set_gate(
        self,
        work_item_id: int | str,
        gate_type: str,
        gate_data: dict | None = None,
        actor: str | None = None,
    ) -> dict:
        """Block a work item on a gate (human input, timer, etc.)."""
        if gate_type not in GateType.ALL:
            raise ValueError(f"Invalid gate_type: {gate_type}. Valid: {GateType.ALL}")

        item = self._resolve_id(work_item_id)
        if not item:
            raise ValueError(f"Work item {work_item_id} not found")

        self.db.execute(
            """UPDATE work_items
               SET gate_type = %s, gate_data = %s::jsonb,
                   gate_resolved_at = NULL, gate_response = NULL,
                   status = 'blocked', updated_at = NOW()
               WHERE id = %s""",
            (gate_type, _json_dumps(gate_data), item["id"]),
        )

        self._log_activity(
            item["id"], actor, ActivityType.GATE_SET,
            f"Gate set: {gate_type}",
            {"gate_type": gate_type, "gate_data": gate_data or {}},
        )
        self.db.commit()

        # Graph sync
        if self.graph and item.get("graph_uuid"):
            try:
                self.graph.update_work_item_gate(item["graph_uuid"], gate_type)
                self.graph.update_work_item_status(item["graph_uuid"], WorkItemStatus.BLOCKED)
            except Exception:
                logger.debug("Graph gate sync failed for work_item #%d", item["id"])

        return {
            "id": item["id"],
            "short_id": item["short_id"],
            "gate_type": gate_type,
            "status": WorkItemStatus.BLOCKED,
            "action": "gate_set",
        }

    @track_operation("work_items.resolve_gate")
    def resolve_gate(
        self,
        work_item_id: int | str,
        response: dict | None = None,
        actor: str | None = None,
    ) -> dict:
        """Resolve a gate, unblocking the work item."""
        item = self._resolve_id(work_item_id)
        if not item:
            raise ValueError(f"Work item {work_item_id} not found")

        if not item.get("gate_type"):
            raise ValueError(f"Work item {item['short_id']} has no active gate")
        if item.get("gate_resolved_at"):
            raise ValueError(f"Gate on {item['short_id']} is already resolved")

        self.db.execute(
            """UPDATE work_items
               SET gate_resolved_at = NOW(), gate_response = %s::jsonb,
                   updated_at = NOW()
               WHERE id = %s""",
            (_json_dumps(response), item["id"]),
        )

        # Check if there are other active blockers
        remaining = self.db.execute_one(
            """SELECT COUNT(*) AS cnt FROM work_item_blocks wb
               JOIN work_items wi ON wi.id = wb.blocker_id
               WHERE wb.blocked_id = %s AND wi.status NOT IN ('done', 'cancelled')""",
            (item["id"],),
        )
        has_other_blockers = remaining and remaining["cnt"] > 0

        new_status = WorkItemStatus.BLOCKED if has_other_blockers else WorkItemStatus.OPEN
        self.db.execute(
            "UPDATE work_items SET status = %s WHERE id = %s",
            (new_status, item["id"]),
        )

        self._log_activity(
            item["id"], actor, ActivityType.GATE_RESOLVED,
            f"Gate resolved: {item['gate_type']}",
            {"gate_type": item["gate_type"], "response": response or {}, "new_status": new_status},
        )
        self.db.commit()

        # Graph sync
        if self.graph and item.get("graph_uuid"):
            try:
                self.graph.resolve_work_item_gate(item["graph_uuid"])
                self.graph.update_work_item_status(item["graph_uuid"], new_status)
            except Exception:
                logger.debug("Graph gate resolve sync failed for work_item #%d", item["id"])

        return {
            "id": item["id"],
            "short_id": item["short_id"],
            "gate_type": item["gate_type"],
            "status": new_status,
            "action": "gate_resolved",
        }

    # ------------------------------------------------------------------
    # Agent heartbeat (v0.48.0)
    # ------------------------------------------------------------------

    @track_operation("work_items.heartbeat")
    def heartbeat(
        self,
        work_item_id: int | str,
        agent_name: str,
        state: str = "working",
        note: str | None = None,
    ) -> dict:
        """Agent reports it's still working. Updates heartbeat timestamp and agent state."""
        if state not in AgentState.ALL:
            state = AgentState.WORKING

        item = self._resolve_id(work_item_id)
        if not item:
            raise ValueError(f"Work item {work_item_id} not found")

        self.db.execute(
            """UPDATE work_items
               SET last_heartbeat = NOW(), agent_state = %s, updated_at = NOW()
               WHERE id = %s""",
            (state, item["id"]),
        )

        # Only log if there's a note (avoid activity spam)
        if note:
            self._log_activity(
                item["id"], agent_name, ActivityType.HEARTBEAT,
                note, {"agent_state": state},
            )

        self.db.commit()
        return {
            "id": item["id"],
            "short_id": item["short_id"],
            "agent_state": state,
            "action": "heartbeat",
        }

    # ------------------------------------------------------------------
    # Activity feed (v0.48.0)
    # ------------------------------------------------------------------

    @track_operation("work_items.activity")
    def get_activity(
        self,
        work_item_id: int | str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Get activity log for a work item."""
        item = self._resolve_id(work_item_id)
        if not item:
            raise ValueError(f"Work item {work_item_id} not found")

        count_row = self.db.execute_one(
            "SELECT COUNT(*) AS total FROM work_item_activity WHERE work_item_id = %s",
            (item["id"],),
        )

        rows = self.db.execute(
            """SELECT id, actor, activity_type, content, metadata, created_at
               FROM work_item_activity
               WHERE work_item_id = %s
               ORDER BY created_at DESC
               LIMIT %s OFFSET %s""",
            (item["id"], limit, offset),
        )

        return {
            "work_item_id": item["id"],
            "short_id": item["short_id"],
            "total": count_row["total"] if count_row else 0,
            "limit": limit,
            "offset": offset,
            "activities": [
                {
                    "id": r["id"],
                    "actor": r["actor"],
                    "activity_type": r["activity_type"],
                    "content": r["content"],
                    "metadata": r["metadata"] or {},
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in rows
            ],
        }

    # ------------------------------------------------------------------
    # Agent briefing (v0.48.0)
    # ------------------------------------------------------------------

    @track_operation("work_items.briefing")
    def generate_briefing(self, work_item_id: int | str) -> dict:
        """Assemble agent briefing context for a work item."""
        item_detail = self.get(work_item_id)

        # Resolve full item row for constraint walking
        item = self._resolve_id(work_item_id)
        all_constraints = self._collect_constraints(item) if item else {}

        # Build parent chain for orientation
        parent_chain = []
        pid = item.get("parent_id") if item else None
        seen = set()
        while pid and pid not in seen:
            seen.add(pid)
            p = self.db.execute_one(
                "SELECT id, short_id, title, parent_id FROM work_items WHERE id = %s",
                (pid,),
            )
            if not p:
                break
            parent_chain.append({"short_id": p["short_id"], "title": p["title"]})
            pid = p.get("parent_id")
        parent_chain.reverse()

        return {
            "work_item": {
                "id": item_detail["id"],
                "short_id": item_detail["short_id"],
                "title": item_detail["title"],
                "description": item_detail.get("description"),
                "acceptance_criteria": item_detail.get("acceptance_criteria"),
                "risk_tier": item_detail.get("risk_tier", 0),
                "risk_label": RiskTier.LABELS.get(item_detail.get("risk_tier", 0), "patrol"),
            },
            "constraints": all_constraints,
            "context": [
                {"id": m["id"], "summary": m.get("summary"), "type": m.get("memory_type")}
                for m in item_detail.get("linked_memories", [])
            ],
            "parent_chain": parent_chain,
        }

    # ------------------------------------------------------------------
    # Gated items query (v0.48.0)
    # ------------------------------------------------------------------

    @track_operation("work_items.gated")
    def gated_items(
        self,
        project: str | None = None,
        gate_type: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Items waiting on gate resolution (the 'needs your input' queue)."""
        conditions = ["wi.gate_type IS NOT NULL", "wi.gate_resolved_at IS NULL"]
        params: list = []

        if project:
            project_id = get_project(self.db, project)
            if project_id is None:
                return {"total": 0, "items": []}
            conditions.append("wi.project_id = %s")
            params.append(project_id)

        if gate_type:
            conditions.append("wi.gate_type = %s")
            params.append(gate_type)

        where = " AND ".join(conditions)

        count_row = self.db.execute_one(
            f"SELECT COUNT(*) AS total FROM work_items wi WHERE {where}",
            tuple(params),
        )

        params.append(limit)
        rows = self.db.execute(
            f"""SELECT wi.id, wi.short_id, wi.title, wi.item_type, wi.priority,
                       wi.status, wi.gate_type, wi.gate_data, wi.risk_tier,
                       p.name AS project
                FROM work_items wi
                LEFT JOIN projects p ON wi.project_id = p.id
                WHERE {where}
                ORDER BY wi.priority DESC, wi.created_at ASC
                LIMIT %s""",
            tuple(params),
        )

        return {
            "total": count_row["total"] if count_row else 0,
            "items": [
                {
                    "id": r["id"],
                    "short_id": r["short_id"],
                    "title": r["title"],
                    "item_type": r["item_type"],
                    "priority": r["priority"],
                    "status": r["status"],
                    "gate_type": r["gate_type"],
                    "gate_data": r["gate_data"] or {},
                    "risk_tier": r["risk_tier"] or 0,
                    "project": r["project"],
                }
                for r in rows
            ],
        }


def _json_dumps(data: dict | None) -> str:
    """Serialize dict to JSON string for Postgres JSONB."""
    import json
    return json.dumps(data or {})
