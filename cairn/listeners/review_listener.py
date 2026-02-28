"""ReviewListener — handles work item state changes when deliverables are reviewed.

On approve: marks linked memories as human-verified, boosts importance.
On revise: reopens work item with reviewer feedback as new constraints.
On reject: cancels work item with rejection reason.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.core.work_items import WorkItemManager
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)

# Importance boost for memories linked to approved deliverables
APPROVAL_IMPORTANCE_BOOST = 0.15
MAX_IMPORTANCE = 1.0


class ReviewListener:
    """Reacts to deliverable review events to update work items and memories."""

    def __init__(
        self,
        work_item_manager: WorkItemManager,
        db: Database,
    ):
        self.work_item_manager = work_item_manager
        self.db = db

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe("deliverable.approved", "review_approve", self._handle_approved)
        event_bus.subscribe("deliverable.revised", "review_revise", self._handle_revised)
        event_bus.subscribe("deliverable.rejected", "review_reject", self._handle_rejected)

    def _handle_approved(self, event: dict) -> None:
        """On approve: verify linked memories (boost importance + tag)."""
        payload = event.get("payload") or {}
        work_item_id = payload.get("work_item_id")
        reviewer = payload.get("reviewer", "human")
        if not work_item_id:
            return

        try:
            self._verify_linked_memories(work_item_id, reviewer)
            logger.info("ReviewListener: approved work item #%d — memories verified", work_item_id)
        except Exception:
            logger.warning(
                "ReviewListener: failed to verify memories for #%d",
                work_item_id, exc_info=True,
            )

    def _handle_revised(self, event: dict) -> None:
        """On revise: reopen work item with reviewer notes as constraints."""
        payload = event.get("payload") or {}
        work_item_id = payload.get("work_item_id")
        reviewer = payload.get("reviewer", "human")
        if not work_item_id:
            return

        try:
            # Get current work item to read existing constraints
            item = self.work_item_manager.get(work_item_id)
            if not item:
                return

            # Get reviewer notes from the deliverable
            reviewer_notes = self._get_reviewer_notes(work_item_id)

            # Merge revision feedback into constraints
            existing_constraints = item.get("constraints") or {}
            revision_history = existing_constraints.get("revision_history", [])
            revision_history.append({
                "version": payload.get("version", 1),
                "reviewer": reviewer,
                "feedback": reviewer_notes,
            })
            existing_constraints["revision_history"] = revision_history
            existing_constraints["revision_feedback"] = reviewer_notes

            # Reopen: clear assignee, set status back to open
            self.work_item_manager.update(
                work_item_id,
                status="open",
                assignee=None,
                constraints=existing_constraints,
            )

            logger.info(
                "ReviewListener: revised work item #%d — reopened with feedback",
                work_item_id,
            )
        except Exception:
            logger.warning(
                "ReviewListener: failed to reopen #%d on revision",
                work_item_id, exc_info=True,
            )

    def _handle_rejected(self, event: dict) -> None:
        """On reject: cancel work item with rejection reason."""
        payload = event.get("payload") or {}
        work_item_id = payload.get("work_item_id")
        if not work_item_id:
            return

        try:
            reviewer_notes = self._get_reviewer_notes(work_item_id)
            self.work_item_manager.update(
                work_item_id,
                status="cancelled",
            )
            # Log the rejection reason in activity
            self.work_item_manager._log_activity(
                work_item_id=work_item_id,
                actor=payload.get("reviewer", "human"),
                activity_type="review",
                content=f"Rejected: {reviewer_notes}" if reviewer_notes else "Rejected",
            )
            logger.info("ReviewListener: rejected work item #%d — cancelled", work_item_id)
        except Exception:
            logger.warning(
                "ReviewListener: failed to cancel #%d on rejection",
                work_item_id, exc_info=True,
            )

    def _verify_linked_memories(self, work_item_id: int, reviewer: str) -> None:
        """Boost importance and tag memories linked to an approved work item."""
        rows = self.db.execute(
            """
            SELECT m.id, m.importance, m.tags
            FROM work_item_memory_links wml
            JOIN memories m ON wml.memory_id = m.id
            WHERE wml.work_item_id = %s AND m.is_active = true
            """,
            (work_item_id,),
        )
        for row in rows:
            new_importance = min(row["importance"] + APPROVAL_IMPORTANCE_BOOST, MAX_IMPORTANCE)
            existing_tags = row.get("tags") or []
            if "human-verified" not in existing_tags:
                existing_tags.append("human-verified")

            self.db.execute(
                "UPDATE memories SET importance = %s, tags = %s WHERE id = %s",
                (new_importance, existing_tags, row["id"]),
            )
        if rows:
            self.db.commit()

    def _get_reviewer_notes(self, work_item_id: int) -> str | None:
        """Get reviewer notes from the latest deliverable."""
        row = self.db.execute_one(
            """
            SELECT reviewer_notes FROM deliverables
            WHERE work_item_id = %s ORDER BY version DESC LIMIT 1
            """,
            (work_item_id,),
        )
        return row["reviewer_notes"] if row else None
