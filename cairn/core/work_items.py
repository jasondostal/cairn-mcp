"""Work item management: hierarchical, graph-native work tracking.

Replaces flat tasks with epics/tasks/subtasks that participate in the
knowledge graph — linked to entities, memories, sessions, and decisions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.analytics import track_operation
from cairn.core.constants import (
    ActivityType,
    AgentState,
    GateType,
    RiskTier,
    WorkItemStatus,
    WorkItemType,
)
from cairn.core.utils import (
    get_or_create_project,
    get_project,
    make_display_id,
    parse_display_id,
)
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.core.extraction import KnowledgeExtractor
    from cairn.embedding.interface import EmbeddingInterface
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
        event_bus: EventBus | None = None,
    ):
        self.db = db
        self.embedding = embedding
        self.graph = graph
        self.knowledge_extractor = knowledge_extractor
        self.event_bus = event_bus

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _publish(
        self, event_type: str, work_item_id: int | None = None,
        project_id: int | None = None, session_name: str | None = None,
        **payload_fields,
    ) -> None:
        """Publish an event if event_bus is available."""
        if not self.event_bus:
            return
        project_name = None
        if project_id:
            row = self.db.execute_one("SELECT name FROM projects WHERE id = %s", (project_id,))
            if row:
                project_name = row["name"]
        try:
            self.event_bus.publish(
                session_name=session_name or "",
                event_type=event_type,
                work_item_id=work_item_id,
                project=project_name,
                payload=payload_fields if payload_fields else None,
            )
        except Exception:
            logger.warning("Failed to publish %s for work_item %s", event_type, work_item_id, exc_info=True)

    def _allocate_seq_num(self, project_id: int) -> int:
        """Atomically allocate the next sequence number for a project."""
        row = self.db.execute_one(
            """UPDATE projects
               SET work_item_next_seq = work_item_next_seq + 1
               WHERE id = %s
               RETURNING work_item_next_seq - 1 AS seq_num""",
            (project_id,),
        )
        assert row is not None
        return row["seq_num"]

    def _display_id(self, item: dict) -> str:
        """Compute display_id for a work item row by fetching project prefix."""
        row = self.db.execute_one(
            "SELECT work_item_prefix FROM projects WHERE id = %s",
            (item["project_id"],),
        )
        prefix = row["work_item_prefix"] if row and row["work_item_prefix"] else "wi"
        return make_display_id(prefix, item["seq_num"])

    def _display_id_from_row(self, r: dict) -> str:
        """Compute display_id from a query row that already has work_item_prefix."""
        prefix = r.get("work_item_prefix") or "wi"
        return make_display_id(prefix, r["seq_num"])

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

    def _resolve_id(self, id_or_display_id: int | str) -> dict | None:
        """Resolve a work item by numeric ID or display ID string (e.g. 'ca-42')."""
        if isinstance(id_or_display_id, int) or (isinstance(id_or_display_id, str) and id_or_display_id.isdigit()):
            return self.db.execute_one(
                "SELECT * FROM work_items WHERE id = %s", (int(id_or_display_id),),
            )
        # Try parsing as display_id (e.g. 'ca-42')
        parsed = parse_display_id(str(id_or_display_id))
        if parsed:
            prefix, seq_num = parsed
            return self.db.execute_one(
                """SELECT wi.* FROM work_items wi
                   JOIN projects p ON wi.project_id = p.id
                   WHERE p.work_item_prefix = %s AND wi.seq_num = %s""",
                (prefix, seq_num),
            )
        return None

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

        # RBAC: set created_by_user_id from current user context (ca-124)
        from cairn.core.user import current_user as _current_user
        _user_ctx = _current_user()
        _created_by = _user_ctx.user_id if _user_ctx else None

        # Allocate sequential number
        seq_num = self._allocate_seq_num(project_id)

        row = self.db.execute_one(
            """
            INSERT INTO work_items
                (project_id, title, description, acceptance_criteria, item_type,
                 priority, parent_id, session_name, embedding, metadata,
                 constraints, risk_tier, seq_num, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
            RETURNING id, created_at
            """,
            (
                project_id, title, description, acceptance_criteria, item_type,
                priority, parent_id, session_name,
                content_embedding, _json_dumps(metadata),
                _json_dumps(constraints), risk_tier or 0, seq_num, _created_by,
            ),
        )
        assert row is not None

        # Compute display_id
        prefix_row = self.db.execute_one(
            "SELECT work_item_prefix FROM projects WHERE id = %s", (project_id,),
        )
        prefix = prefix_row["work_item_prefix"] if prefix_row and prefix_row["work_item_prefix"] else "wi"
        display_id = make_display_id(prefix, seq_num)

        # Log creation activity
        self._log_activity(
            row["id"], None, ActivityType.CREATED,
            f"Created {item_type}: {title}",
            {"item_type": item_type, "priority": priority, "risk_tier": risk_tier or 0},
        )

        # Link creating session
        self.link_session(row["id"], session_name, "created")

        self.db.commit()

        # Risk tier CRITICAL auto-gates with human gate
        if risk_tier == RiskTier.CRITICAL:
            self.set_gate(
                row["id"], GateType.HUMAN,
                gate_data={"question": "This is a CRITICAL risk item. Confirm before proceeding.", "auto_set": True},
            )

        # Event-driven graph projection
        self._publish(
            "work_item.created", work_item_id=row["id"],
            project_id=project_id, session_name=session_name,
            short_id=display_id,
        )

        logger.info("Created work item %s (#%d) for project %s", display_id, row["id"], project)
        return {
            "id": row["id"],
            "display_id": display_id,
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
    def update(self, id_or_display_id: int | str, **fields) -> dict:
        """Update work item fields. Validates status transitions."""
        calling_session = fields.pop("_calling_session", None)

        item = self._resolve_id(id_or_display_id)
        if not item:
            raise ValueError(f"Work item {id_or_display_id} not found")

        display_id = self._display_id(item)

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
                    "risk_tier", "constraints", "parent_id"}
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
            return {"id": item["id"], "display_id": display_id, "action": "no_changes"}

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

        self.link_session(item["id"], calling_session, "updated")
        self.db.commit()

        # Event-driven graph projection
        if new_status:
            self._publish(
                "work_item.status_changed", work_item_id=item["id"],
                project_id=item["project_id"], session_name=calling_session,
                old_status=item["status"], new_status=new_status,
            )
        elif fields:
            self._publish(
                "work_item.updated", work_item_id=item["id"],
                project_id=item["project_id"], session_name=calling_session,
                fields_changed=list(fields.keys()),
            )

        return {"id": item["id"], "display_id": display_id, "action": "updated"}

    @track_operation("work_items.claim")
    def claim(self, work_item_id: int | str, assignee: str, session_name: str | None = None) -> dict:
        """Atomically claim a work item (open/ready → in_progress)."""
        item = self._resolve_id(work_item_id)
        if not item:
            raise ValueError(f"Work item {work_item_id} not found")

        display_id = self._display_id(item)

        row = self.db.execute_one(
            """
            UPDATE work_items
            SET status = 'in_progress', assignee = %s, claimed_at = NOW(), updated_at = NOW()
            WHERE id = %s AND status IN ('open', 'ready')
            RETURNING id
            """,
            (assignee, item["id"]),
        )
        if not row:
            raise ValueError(
                f"Cannot claim work item {display_id} — "
                f"status is '{item['status']}' (must be open or ready)"
            )

        self._log_activity(
            item["id"], assignee, ActivityType.CLAIM,
            f"Claimed by {assignee}",
            {"assignee": assignee, "old_status": item["status"]},
        )
        self.link_session(item["id"], session_name, "claimed")
        self.db.commit()

        # Event-driven graph projection
        self._publish(
            "work_item.claimed", work_item_id=item["id"],
            project_id=item["project_id"], session_name=session_name,
            assignee=assignee,
        )

        return {
            "id": row["id"],
            "display_id": display_id,
            "assignee": assignee,
            "status": WorkItemStatus.IN_PROGRESS,
            "action": "claimed",
        }

    @track_operation("work_items.complete")
    def complete(self, work_item_id: int | str, session_name: str | None = None) -> dict:
        """Mark a work item as done and auto-unblock dependents."""
        item = self._resolve_id(work_item_id)
        if not item:
            raise ValueError(f"Work item {work_item_id} not found")

        display_id = self._display_id(item)

        if item["status"] in WorkItemStatus.TERMINAL:
            raise ValueError(f"Work item {display_id} is already {item['status']}")

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
        self.link_session(item["id"], session_name, "completed")

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

        # Event-driven graph projection
        self._publish(
            "work_item.completed", work_item_id=item["id"],
            project_id=item["project_id"], session_name=session_name,
            old_status=item["status"],
        )

        return {"id": item["id"], "display_id": display_id, "action": "completed"}

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

        # Event-driven graph projection
        self._publish(
            "work_item.blocked",
            work_item_id=blocker["id"],
            project_id=blocker["project_id"],
            blocker_id=blocker["id"], blocked_id=blocked["id"],
        )

        return {
            "blocker": {"id": blocker["id"], "display_id": self._display_id(blocker)},
            "blocked": {"id": blocked["id"], "display_id": self._display_id(blocked)},
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

        # Event-driven graph projection
        self._publish(
            "work_item.unblocked",
            work_item_id=blocker["id"],
            project_id=blocker["project_id"],
            blocker_id=blocker["id"], blocked_id=blocked["id"],
        )

        return {
            "blocker": {"id": blocker["id"], "display_id": self._display_id(blocker)},
            "blocked": {"id": blocked["id"], "display_id": self._display_id(blocked)},
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

        # RBAC: scope to user's accessible projects (ca-124)
        from cairn.core.user import current_user
        user_ctx = current_user()
        if user_ctx is not None and user_ctx.role != "admin":
            conditions.append("wi.project_id = ANY(%s)")
            params.append(list(user_ctx.project_ids))

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

        query = f"""
            SELECT wi.id, wi.seq_num, wi.title, wi.item_type, wi.priority,
                   wi.status, wi.assignee, wi.parent_id, wi.session_name,
                   wi.risk_tier, wi.gate_type, wi.agent_state,
                   wi.created_at, wi.updated_at, wi.completed_at, wi.cancelled_at,
                   p.name AS project, p.work_item_prefix,
                   COALESCE(cc.cnt, 0) AS children_count,
                   COUNT(*) OVER() AS _total
            FROM work_items wi
            LEFT JOIN projects p ON wi.project_id = p.id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM work_items c WHERE c.parent_id = wi.id
            ) cc ON true
            WHERE {where}
            ORDER BY wi.priority DESC, wi.created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        rows = self.db.execute(query, tuple(params))
        total = rows[0]["_total"] if rows else 0

        # When include_children is requested without a parent_id, fetch all
        # descendants of the items in the result set so the UI can build a
        # complete tree. Without this, children beyond the LIMIT are invisible.
        if include_children and parent_id is None and rows:
            returned_ids = {r["id"] for r in rows}
            parents_with_children = [
                r["id"] for r in rows if r["children_count"] > 0
            ]
            if parents_with_children:
                # Recursively collect all descendants of items in the result
                ph = ", ".join(["%s"] * len(parents_with_children))
                child_rows = self.db.execute(
                    f"""
                    WITH RECURSIVE descendants AS (
                        SELECT id FROM work_items WHERE parent_id IN ({ph})
                        UNION
                        SELECT c.id FROM work_items c
                        JOIN descendants d ON c.parent_id = d.id
                    )
                    SELECT wi.id, wi.seq_num, wi.title, wi.item_type, wi.priority,
                           wi.status, wi.assignee, wi.parent_id, wi.session_name,
                           wi.risk_tier, wi.gate_type, wi.agent_state,
                           wi.created_at, wi.updated_at, wi.completed_at, wi.cancelled_at,
                           p.name AS project, p.work_item_prefix,
                           COALESCE(cc.cnt, 0) AS children_count,
                           0 AS _total
                    FROM work_items wi
                    JOIN descendants d ON wi.id = d.id
                    LEFT JOIN projects p ON wi.project_id = p.id
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS cnt FROM work_items c WHERE c.parent_id = wi.id
                    ) cc ON true
                    WHERE wi.id NOT IN ({", ".join(["%s"] * len(returned_ids))})
                    ORDER BY wi.priority DESC, wi.created_at DESC
                    """,
                    tuple(parents_with_children) + tuple(returned_ids),
                )
                # Deduplicate — belt-and-suspenders against CTE multi-path traversal
                new_rows = [r for r in child_rows if r["id"] not in returned_ids]
                rows = list(rows) + new_rows

        items = [
            {
                "id": r["id"],
                "display_id": self._display_id_from_row(r),
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
            SELECT wi.id, wi.title, wi.priority, wi.seq_num, wi.item_type,
                   p.work_item_prefix
            FROM work_items wi
            LEFT JOIN projects p ON wi.project_id = p.id
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
            "items": [
                {
                    "id": r["id"],
                    "display_id": self._display_id_from_row(r),
                    "title": r["title"],
                    "priority": r["priority"],
                    "item_type": r["item_type"],
                }
                for r in rows
            ],
            "source": "postgres",
        }

    @track_operation("work_items.get")
    def get(self, id_or_display_id: int | str) -> dict:
        """Full detail for a single work item."""
        item = self._resolve_id(id_or_display_id)
        if not item:
            raise ValueError(f"Work item {id_or_display_id} not found")

        display_id = self._display_id(item)

        # Project name
        proj = self.db.execute_one(
            "SELECT name FROM projects WHERE id = %s", (item["project_id"],),
        )

        # Parent info
        parent_info = None
        if item["parent_id"]:
            parent = self.db.execute_one(
                """SELECT wi.id, wi.seq_num, wi.title, p.work_item_prefix
                   FROM work_items wi
                   JOIN projects p ON wi.project_id = p.id
                   WHERE wi.id = %s""",
                (item["parent_id"],),
            )
            if parent:
                parent_info = {
                    "id": parent["id"],
                    "display_id": self._display_id_from_row(parent),
                    "title": parent["title"],
                }

        # Children count
        children = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM work_items WHERE parent_id = %s",
            (item["id"],),
        )

        # Blockers
        blockers = self.db.execute(
            """
            SELECT wi.id, wi.seq_num, wi.title, wi.status, p.work_item_prefix
            FROM work_item_blocks wb
            JOIN work_items wi ON wi.id = wb.blocker_id
            JOIN projects p ON wi.project_id = p.id
            WHERE wb.blocked_id = %s
            """,
            (item["id"],),
        )

        # Blocking (items this blocks)
        blocking = self.db.execute(
            """
            SELECT wi.id, wi.seq_num, wi.title, wi.status, p.work_item_prefix
            FROM work_item_blocks wb
            JOIN work_items wi ON wi.id = wb.blocked_id
            JOIN projects p ON wi.project_id = p.id
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

        # Linked sessions
        linked_sessions = self.sessions_for_work_item(item["id"])

        return {
            "id": item["id"],
            "display_id": display_id,
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
            "blockers": [
                {"id": b["id"], "display_id": self._display_id_from_row(b), "title": b["title"], "status": b["status"]}
                for b in blockers
            ],
            "blocking": [
                {"id": b["id"], "display_id": self._display_id_from_row(b), "title": b["title"], "status": b["status"]}
                for b in blocking
            ],
            "linked_memories": [dict(m) for m in linked],
            "linked_sessions": linked_sessions,
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

        # Event-driven graph projection
        self._publish(
            "work_item.memories_linked", work_item_id=item["id"],
            project_id=item["project_id"],
            memory_ids=memory_ids,
        )

        return {
            "work_item_id": item["id"],
            "display_id": self._display_id(item),
            "linked": memory_ids,
        }

    # ------------------------------------------------------------------
    # Session ↔ Work Item linking (v0.51.0)
    # ------------------------------------------------------------------

    # Role escalation order — higher index wins on conflict.
    _ROLE_ORDER = ["touch", "heartbeat", "updated", "created", "claimed", "completed"]

    def link_session(
        self,
        work_item_id: int,
        session_name: str | None,
        role: str = "touch",
    ) -> None:
        """Upsert a session ↔ work-item link. Idempotent.

        Repeated calls bump last_seen and touch_count.
        Role only escalates (completed > claimed > created > updated > heartbeat > touch).
        """
        if not session_name:
            return

        if role not in self._ROLE_ORDER:
            role = "touch"

        self.db.execute(
            """
            INSERT INTO session_work_items (session_name, work_item_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (session_name, work_item_id) DO UPDATE SET
                last_seen   = NOW(),
                touch_count = session_work_items.touch_count + 1,
                role        = CASE
                    WHEN array_position(
                            ARRAY['touch','heartbeat','updated','created','claimed','completed'],
                            EXCLUDED.role
                         ) >
                         array_position(
                            ARRAY['touch','heartbeat','updated','created','claimed','completed'],
                            session_work_items.role
                         )
                    THEN EXCLUDED.role
                    ELSE session_work_items.role
                END
            """,
            (session_name, work_item_id, role),
        )

    def sessions_for_work_item(self, work_item_id: int | str) -> list[dict]:
        """Return sessions linked to a work item, newest first."""
        item = self._resolve_id(work_item_id)
        if not item:
            return []

        rows = self.db.execute(
            """
            SELECT swi.session_name, swi.role, swi.first_seen, swi.last_seen,
                   swi.touch_count,
                   s.id AS session_id, s.closed_at,
                   (s.closed_at IS NULL AND s.id IS NOT NULL) AS is_active
            FROM session_work_items swi
            LEFT JOIN sessions s ON s.session_name = swi.session_name
            WHERE swi.work_item_id = %s
            ORDER BY swi.last_seen DESC
            """,
            (item["id"],),
        )
        return [
            {
                "session_name": r["session_name"],
                "role": r["role"],
                "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
                "touch_count": r["touch_count"],
                "is_active": bool(r["is_active"]),
            }
            for r in rows
        ]

    def work_items_for_session(self, session_name: str) -> list[dict]:
        """Return work items linked to a session, newest first."""
        rows = self.db.execute(
            """
            SELECT wi.id, wi.seq_num, wi.title, wi.status, wi.item_type,
                   wi.priority, wi.assignee,
                   p.name AS project, p.work_item_prefix,
                   swi.role, swi.first_seen, swi.last_seen, swi.touch_count
            FROM session_work_items swi
            JOIN work_items wi ON wi.id = swi.work_item_id
            LEFT JOIN projects p ON wi.project_id = p.id
            WHERE swi.session_name = %s
            ORDER BY swi.last_seen DESC
            """,
            (session_name,),
        )
        return [
            {
                "id": r["id"],
                "display_id": self._display_id_from_row(r),
                "title": r["title"],
                "status": r["status"],
                "item_type": r["item_type"],
                "priority": r["priority"],
                "assignee": r["assignee"],
                "project": r["project"],
                "role": r["role"],
                "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
                "touch_count": r["touch_count"],
            }
            for r in rows
        ]

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

        # Event-driven graph projection
        self._publish(
            "work_item.gate_set", work_item_id=item["id"],
            project_id=item["project_id"],
            gate_type=gate_type,
        )

        return {
            "id": item["id"],
            "display_id": self._display_id(item),
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

        display_id = self._display_id(item)

        if not item.get("gate_type"):
            raise ValueError(f"Work item {display_id} has no active gate")
        if item.get("gate_resolved_at"):
            raise ValueError(f"Gate on {display_id} is already resolved")

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

        # Event-driven graph projection
        self._publish(
            "work_item.gate_resolved", work_item_id=item["id"],
            project_id=item["project_id"],
            new_status=new_status,
        )

        return {
            "id": item["id"],
            "display_id": display_id,
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
        session_name: str | None = None,
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

        self.link_session(item["id"], session_name, "heartbeat")
        self.db.commit()
        return {
            "id": item["id"],
            "display_id": self._display_id(item),
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
            "display_id": self._display_id(item),
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
                """SELECT wi.id, wi.seq_num, wi.title, wi.parent_id, p.work_item_prefix
                   FROM work_items wi
                   JOIN projects p ON wi.project_id = p.id
                   WHERE wi.id = %s""",
                (pid,),
            )
            if not p:
                break
            parent_chain.append({"display_id": self._display_id_from_row(p), "title": p["title"]})
            pid = p.get("parent_id")
        parent_chain.reverse()

        return {
            "work_item": {
                "id": item_detail["id"],
                "display_id": item_detail["display_id"],
                "title": item_detail["title"],
                "description": item_detail.get("description"),
                "item_type": item_detail.get("item_type", "task"),
                "acceptance_criteria": item_detail.get("acceptance_criteria"),
                "risk_tier": item_detail.get("risk_tier", 0),
                "risk_label": RiskTier.LABELS.get(item_detail.get("risk_tier", 0), "patrol"),
                "status": item_detail.get("status"),
                "gate_type": item_detail.get("gate_type"),
                "gate_data": item_detail.get("gate_data"),
                "gate_response": item_detail.get("gate_response"),
            },
            "constraints": all_constraints,
            "context": [
                {"id": m["id"], "summary": m.get("summary"), "type": m.get("memory_type")}
                for m in item_detail.get("linked_memories", [])
            ],
            "parent_chain": parent_chain,
        }

    @track_operation("work_items.decomposition_context")
    def decomposition_context(self, work_item_id: int | str) -> dict:
        """Assemble context for epic decomposition by a coordinator agent.

        Returns the epic details plus existing children (if any), so the
        coordinator can reason about what subtasks to create, what's already
        been decomposed, and what dependencies exist.
        """
        briefing = self.generate_briefing(work_item_id)

        # Fetch existing children
        item = self._resolve_id(work_item_id)
        existing_children = []
        if item:
            rows = self.db.execute(
                """SELECT wi.id, wi.seq_num, wi.title, wi.description,
                          wi.status, wi.item_type, wi.priority, wi.risk_tier,
                          wi.assignee, p.work_item_prefix
                   FROM work_items wi
                   JOIN projects p ON wi.project_id = p.id
                   WHERE wi.parent_id = %s
                   ORDER BY wi.priority DESC, wi.created_at ASC""",
                (item["id"],),
            )
            for r in rows:
                existing_children.append({
                    "display_id": self._display_id_from_row(r),
                    "title": r["title"],
                    "description": r.get("description"),
                    "status": r["status"],
                    "item_type": r["item_type"],
                    "priority": r["priority"],
                    "risk_tier": r.get("risk_tier", 0),
                    "assignee": r.get("assignee"),
                })

        return {
            **briefing,
            "existing_children": existing_children,
            "children_count": len(existing_children),
            "is_re_decomposition": len(existing_children) > 0,
        }

    # ------------------------------------------------------------------
    # Progress monitoring (v0.65.0 — ca-152)
    # ------------------------------------------------------------------

    @track_operation("work_items.progress_summary")
    def progress_summary(
        self,
        work_item_id: int | str,
        stale_threshold_minutes: int = 10,
    ) -> dict:
        """Aggregate progress of all subtasks under a parent work item.

        Returns status counts, stale/stuck agents, blocked items, and a
        human-readable progress line. Used by coordinators to monitor workers.
        """
        item = self._resolve_id(work_item_id)
        if not item:
            raise ValueError(f"Work item {work_item_id} not found")

        rows = self.db.execute(
            """SELECT wi.id, wi.seq_num, wi.title, wi.status, wi.assignee,
                      wi.agent_state, wi.last_heartbeat, wi.gate_type,
                      wi.risk_tier, wi.item_type,
                      p.work_item_prefix,
                      EXTRACT(EPOCH FROM (NOW() - wi.last_heartbeat)) / 60.0
                          AS heartbeat_age_minutes
               FROM work_items wi
               JOIN projects p ON wi.project_id = p.id
               WHERE wi.parent_id = %s
               ORDER BY wi.priority DESC, wi.created_at ASC""",
            (item["id"],),
        )

        # Status counts
        status_counts: dict[str, int] = {}
        stale_agents: list[dict] = []
        blocked_items: list[dict] = []
        children: list[dict] = []

        for r in rows:
            status = r["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
            display_id = self._display_id_from_row(r)

            child_info = {
                "display_id": display_id,
                "title": r["title"],
                "status": status,
                "assignee": r.get("assignee"),
                "agent_state": r.get("agent_state"),
                "heartbeat_age_minutes": round(r["heartbeat_age_minutes"], 1) if r.get("heartbeat_age_minutes") else None,
            }
            children.append(child_info)

            # Detect stale agents
            if (status == "in_progress"
                    and r.get("heartbeat_age_minutes") is not None
                    and r["heartbeat_age_minutes"] > stale_threshold_minutes):
                stale_agents.append({
                    "display_id": display_id,
                    "title": r["title"],
                    "assignee": r.get("assignee"),
                    "heartbeat_age_minutes": round(r["heartbeat_age_minutes"], 1),
                    "agent_state": r.get("agent_state"),
                })

            # Detect blocked/gated items
            if r.get("gate_type") or status == "blocked":
                blocked_items.append({
                    "display_id": display_id,
                    "title": r["title"],
                    "gate_type": r.get("gate_type"),
                    "status": status,
                })

        total = len(rows)
        done = status_counts.get("done", 0)
        in_progress = status_counts.get("in_progress", 0)
        blocked = status_counts.get("blocked", 0)

        # Human-readable progress line
        progress_line = f"{done}/{total} complete"
        if in_progress:
            progress_line += f", {in_progress} in progress"
        if blocked:
            progress_line += f", {blocked} blocked"
        if stale_agents:
            progress_line += f", {len(stale_agents)} stale"

        return {
            "parent_display_id": self._display_id(item),
            "total_children": total,
            "status_counts": status_counts,
            "progress_line": progress_line,
            "all_complete": done == total and total > 0,
            "stale_agents": stale_agents,
            "blocked_items": blocked_items,
            "children": children,
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
            f"""SELECT wi.id, wi.seq_num, wi.title, wi.item_type, wi.priority,
                       wi.status, wi.gate_type, wi.gate_data, wi.risk_tier,
                       p.name AS project, p.work_item_prefix
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
                    "display_id": self._display_id_from_row(r),
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
