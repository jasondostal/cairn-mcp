"""Deliverable management — structured agent output for human review.

Part of ca-136 Human/Agent Collaboration & Multi-Agent Orchestration (Tier 1).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from cairn.core.constants import DeliverableStatus
from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class DeliverableManager:
    """Handles deliverable lifecycle: create, review, query."""

    def __init__(self, db: Database, event_bus=None):
        self.db = db
        self.event_bus = event_bus

    def create(
        self,
        work_item_id: int,
        summary: str,
        changes: list[dict] | None = None,
        decisions: list[dict] | None = None,
        open_items: list[dict] | None = None,
        metrics: dict | None = None,
        status: str = DeliverableStatus.DRAFT,
    ) -> dict:
        """Create a deliverable for a work item.

        Increments version automatically if a prior deliverable exists.
        """
        # Get next version
        row = self.db.execute_one(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next_ver FROM deliverables WHERE work_item_id = %s",
            (work_item_id,),
        )
        assert row is not None
        next_version = row["next_ver"]

        result = self.db.execute_one(
            """
            INSERT INTO deliverables (work_item_id, version, status, summary, changes, decisions, open_items, metrics)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, version, status, created_at
            """,
            (
                work_item_id,
                next_version,
                status,
                summary,
                json.dumps(changes or []),
                json.dumps(decisions or []),
                json.dumps(open_items or []),
                json.dumps(metrics or {}),
            ),
        )
        assert result is not None

        self._publish("deliverable.created", {
            "deliverable_id": result["id"],
            "work_item_id": work_item_id,
            "version": next_version,
            "status": status,
        })

        return {
            "id": result["id"],
            "work_item_id": work_item_id,
            "version": result["version"],
            "status": result["status"],
            "created_at": result["created_at"].isoformat() if result["created_at"] else None,
        }

    def get(self, work_item_id: int, version: int | None = None) -> dict | None:
        """Get deliverable for a work item. Latest version if version not specified."""
        if version:
            row = self.db.execute_one(
                "SELECT * FROM deliverables WHERE work_item_id = %s AND version = %s",
                (work_item_id, version),
            )
        else:
            row = self.db.execute_one(
                "SELECT * FROM deliverables WHERE work_item_id = %s ORDER BY version DESC LIMIT 1",
                (work_item_id,),
            )
        if not row:
            return None
        return self._row_to_dict(row)

    def get_by_id(self, deliverable_id: int) -> dict | None:
        """Get deliverable by its own ID."""
        row = self.db.execute_one(
            "SELECT * FROM deliverables WHERE id = %s",
            (deliverable_id,),
        )
        if not row:
            return None
        return self._row_to_dict(row)

    def review(
        self,
        work_item_id: int,
        action: str,
        reviewer: str | None = None,
        notes: str | None = None,
    ) -> dict:
        """Review a deliverable: approve, revise, or reject.

        Args:
            work_item_id: The work item whose latest deliverable to review.
            action: One of 'approve', 'revise', 'reject'.
            reviewer: Who performed the review.
            notes: Review comments (required for revise/reject).
        """
        valid_actions = {"approve", "revise", "reject"}
        if action not in valid_actions:
            raise ValueError(f"Invalid review action: {action}. Must be one of {valid_actions}")

        deliverable = self.get(work_item_id)
        if not deliverable:
            raise ValueError(f"No deliverable found for work item {work_item_id}")

        if deliverable["status"] not in (DeliverableStatus.DRAFT, DeliverableStatus.PENDING_REVIEW):
            raise ValueError(
                f"Deliverable is in '{deliverable['status']}' status, cannot review. "
                f"Only 'draft' or 'pending_review' deliverables can be reviewed."
            )

        status_map = {
            "approve": DeliverableStatus.APPROVED,
            "revise": DeliverableStatus.REVISED,
            "reject": DeliverableStatus.REJECTED,
        }
        new_status = status_map[action]
        now = datetime.now(UTC)

        self.db.execute(
            """
            UPDATE deliverables
            SET status = %s, reviewer_notes = %s, reviewed_by = %s, reviewed_at = %s, updated_at = %s
            WHERE id = %s
            """,
            (new_status, notes, reviewer, now, now, deliverable["id"]),
        )

        self._publish(f"deliverable.{action}d", {
            "deliverable_id": deliverable["id"],
            "work_item_id": work_item_id,
            "version": deliverable["version"],
            "status": new_status,
            "reviewer": reviewer,
        })

        return {
            "id": deliverable["id"],
            "work_item_id": work_item_id,
            "version": deliverable["version"],
            "status": new_status,
            "action": action,
            "reviewed_by": reviewer,
            "reviewed_at": now.isoformat(),
        }

    def list_pending(
        self,
        project: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """List deliverables pending review, optionally filtered by project."""
        if project:
            rows = self.db.execute(
                """
                SELECT d.*, w.title AS work_item_title, p.name AS project_name
                FROM deliverables d
                JOIN work_items w ON d.work_item_id = w.id
                JOIN projects p ON w.project_id = p.id
                WHERE d.status IN ('draft', 'pending_review')
                AND p.name = %s
                ORDER BY d.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (project, limit, offset),
            )
        else:
            rows = self.db.execute(
                """
                SELECT d.*, w.title AS work_item_title, p.name AS project_name
                FROM deliverables d
                JOIN work_items w ON d.work_item_id = w.id
                JOIN projects p ON w.project_id = p.id
                WHERE d.status IN ('draft', 'pending_review')
                ORDER BY d.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
        return {
            "items": [self._row_to_dict(r) for r in rows],
            "limit": limit,
            "offset": offset,
        }

    def list_for_work_item(self, work_item_id: int) -> list[dict]:
        """Get all deliverable versions for a work item."""
        rows = self.db.execute(
            "SELECT * FROM deliverables WHERE work_item_id = %s ORDER BY version DESC",
            (work_item_id,),
        )
        return [self._row_to_dict(r) for r in rows]

    def submit_for_review(self, work_item_id: int) -> dict:
        """Move latest draft deliverable to pending_review status."""
        deliverable = self.get(work_item_id)
        if not deliverable:
            raise ValueError(f"No deliverable found for work item {work_item_id}")
        if deliverable["status"] != DeliverableStatus.DRAFT:
            raise ValueError(f"Deliverable is '{deliverable['status']}', not 'draft'")

        now = datetime.now(UTC)
        self.db.execute(
            "UPDATE deliverables SET status = %s, updated_at = %s WHERE id = %s",
            (DeliverableStatus.PENDING_REVIEW, now, deliverable["id"]),
        )

        self._publish("deliverable.submitted", {
            "deliverable_id": deliverable["id"],
            "work_item_id": work_item_id,
            "version": deliverable["version"],
        })

        return {
            "id": deliverable["id"],
            "work_item_id": work_item_id,
            "version": deliverable["version"],
            "status": DeliverableStatus.PENDING_REVIEW,
        }

    def collect_child_deliverables(self, parent_work_item_id: int) -> list[dict]:
        """Collect deliverables from all child work items of a parent.

        Returns the latest deliverable for each child, enriched with work item
        title and status. Used by coordinators for result synthesis.
        """
        rows = self.db.execute(
            """SELECT DISTINCT ON (wi.id)
                      d.*, wi.title AS work_item_title, wi.status AS work_item_status,
                      wi.seq_num, p.work_item_prefix
               FROM work_items wi
               JOIN deliverables d ON d.work_item_id = wi.id
               JOIN projects p ON wi.project_id = p.id
               WHERE wi.parent_id = %s
               ORDER BY wi.id, d.version DESC""",
            (parent_work_item_id,),
        )
        result = []
        for r in rows:
            d = self._row_to_dict(r)
            d["work_item_title"] = r.get("work_item_title")
            d["work_item_status"] = r.get("work_item_status")
            d["display_id"] = f"{r.get('work_item_prefix', 'ca')}-{r.get('seq_num', r['work_item_id'])}"
            result.append(d)
        return result

    def synthesize_epic(
        self,
        parent_work_item_id: int,
        *,
        summary_override: str | None = None,
    ) -> dict:
        """Create an epic-level deliverable by synthesizing child deliverables.

        Mechanically aggregates changes, decisions, open items, and metrics
        from all child deliverables. If summary_override is provided, uses that
        instead of auto-generating.

        For LLM-powered synthesis, the coordinator agent calls this method
        and provides its own synthesized summary.
        """
        children = self.collect_child_deliverables(parent_work_item_id)
        if not children:
            raise ValueError(f"No child deliverables found for work item {parent_work_item_id}")

        # Aggregate changes across all children
        all_changes: list[dict] = []
        all_decisions: list[dict] = []
        all_open_items: list[dict] = []
        total_metrics: dict = {}

        for child in children:
            child_label = f"{child.get('display_id', '?')}: {child.get('work_item_title', '?')}"

            for change in (child.get("changes") or []):
                change_copy = dict(change)
                change_copy["source"] = child_label
                all_changes.append(change_copy)

            for decision in (child.get("decisions") or []):
                decision_copy = dict(decision)
                decision_copy["source"] = child_label
                all_decisions.append(decision_copy)

            for item in (child.get("open_items") or []):
                item_copy = dict(item)
                item_copy["source"] = child_label
                all_open_items.append(item_copy)

            # Aggregate numeric metrics
            for key, val in (child.get("metrics") or {}).items():
                if isinstance(val, (int, float)):
                    total_metrics[key] = total_metrics.get(key, 0) + val

        # Add synthesis-specific metrics
        total_metrics["child_deliverables"] = len(children)
        total_metrics["approved_count"] = sum(
            1 for c in children if c.get("status") == "approved"
        )

        # Auto-generate summary if none provided
        if summary_override:
            summary = summary_override
        else:
            child_summaries = []
            for child in children:
                status = child.get("work_item_status", "?")
                child_summaries.append(
                    f"- **{child.get('display_id', '?')}** ({status}): "
                    f"{(child.get('summary') or 'no summary')[:200]}"
                )
            summary = (
                f"Epic synthesis — {len(children)} subtask deliverable(s):\n\n"
                + "\n".join(child_summaries)
            )

        return self.create(
            work_item_id=parent_work_item_id,
            summary=summary,
            changes=all_changes,
            decisions=all_decisions,
            open_items=all_open_items,
            metrics=total_metrics,
            status=DeliverableStatus.DRAFT,
        )

    def _row_to_dict(self, row: dict) -> dict:
        """Convert a DB row to a clean dict."""
        d = dict(row)
        for ts_field in ("created_at", "updated_at", "reviewed_at"):
            if d.get(ts_field) and hasattr(d[ts_field], "isoformat"):
                d[ts_field] = d[ts_field].isoformat()
        # Ensure JSONB fields are dicts/lists not strings
        for json_field in ("changes", "decisions", "open_items", "metrics"):
            if isinstance(d.get(json_field), str):
                d[json_field] = json.loads(d[json_field])
        return d

    def _publish(self, event_type: str, data: dict) -> None:
        """Publish event to event bus if available."""
        if self.event_bus:
            try:
                self.event_bus.publish(event_type, data)
            except Exception:
                logger.warning("Failed to publish %s event", event_type, exc_info=True)
