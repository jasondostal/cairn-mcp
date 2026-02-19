"""Graph projection listener — event-driven Neo4j sync.

Replaces inline dual-write pattern. Subscribes to work_item.*, task.*,
and thinking.* events. Each handler queries PG for current state and
calls idempotent ensure_* methods on the graph provider. Backfills
graph_uuid in PG if it was missing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.graph.interface import GraphProvider
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class GraphProjectionListener:
    """Event-driven graph projection for work items, tasks, and thinking."""

    def __init__(self, graph: GraphProvider, db: Database):
        self.graph = graph
        self.db = db

    def register(self, event_bus: EventBus) -> None:
        """Subscribe to all graph-relevant event types."""
        event_bus.subscribe("work_item.*", "graph_projection", self.handle)
        event_bus.subscribe("task.*", "graph_projection", self.handle)
        event_bus.subscribe("thinking.*", "graph_projection", self.handle)

    def handle(self, event: dict) -> None:
        """Route event to the appropriate handler."""
        router = {
            # Work items
            "work_item.created": self._wi_ensure,
            "work_item.status_changed": self._wi_ensure,
            "work_item.completed": self._wi_ensure,
            "work_item.claimed": self._wi_ensure,
            "work_item.updated": self._wi_ensure,
            "work_item.blocked": self._wi_blocked,
            "work_item.unblocked": self._wi_unblocked,
            "work_item.gate_set": self._wi_ensure,
            "work_item.gate_resolved": self._wi_ensure,
            "work_item.memories_linked": self._wi_memories_linked,
            # Tasks
            "task.created": self._task_ensure,
            "task.completed": self._task_ensure,
            "task.memories_linked": self._task_memories_linked,
            # Thinking
            "thinking.sequence_started": self._thinking_ensure,
            "thinking.thought_added": self._thought_ensure,
            "thinking.sequence_concluded": self._thinking_ensure,
        }
        handler = router.get(event["event_type"])
        if handler:
            handler(event)
        else:
            logger.debug("GraphProjection: no handler for %s", event["event_type"])

    # ------------------------------------------------------------------
    # Work items
    # ------------------------------------------------------------------

    def _wi_ensure(self, event: dict) -> None:
        """Ensure work item node exists and matches PG state."""
        wi_id = event.get("work_item_id") or event["payload"].get("work_item_id")
        if not wi_id:
            logger.warning("GraphProjection: work_item event missing work_item_id")
            return

        row = self.db.execute_one("SELECT * FROM work_items WHERE id = %s", (wi_id,))
        if not row:
            logger.warning("GraphProjection: work_item %d not found in PG", wi_id)
            return

        now = datetime.now(timezone.utc).isoformat()
        graph_uuid = self.graph.ensure_work_item(
            pg_id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            description=row.get("description") or "",
            item_type=row["item_type"],
            priority=row["priority"],
            status=row["status"],
            short_id=row["short_id"],
            risk_tier=row.get("risk_tier", 0),
            gate_type=row.get("gate_type"),
            assignee=row.get("assignee"),
            completed_at=row["completed_at"].isoformat() if row.get("completed_at") else None,
        )

        # Backfill graph_uuid in PG if missing
        if not row.get("graph_uuid"):
            self.db.execute(
                "UPDATE work_items SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                (graph_uuid, row["id"]),
            )
            self.db.commit()
            logger.info("GraphProjection: backfilled graph_uuid for work_item #%d", row["id"])

        # Handle parent edge
        if row.get("parent_id"):
            parent = self.db.execute_one("SELECT id, project_id FROM work_items WHERE id = %s", (row["parent_id"],))
            if parent:
                parent_uuid = self.graph.ensure_work_item(
                    pg_id=parent["id"], project_id=parent["project_id"],
                )
                self.graph.add_work_item_parent_edge(child_uuid=graph_uuid, parent_uuid=parent_uuid)

    def _wi_blocked(self, event: dict) -> None:
        """Create BLOCKS edge between two work items."""
        payload = event["payload"]
        blocker_id = payload.get("blocker_id")
        blocked_id = payload.get("blocked_id")
        if not blocker_id or not blocked_id:
            return

        blocker = self.db.execute_one("SELECT id, project_id FROM work_items WHERE id = %s", (blocker_id,))
        blocked = self.db.execute_one("SELECT id, project_id FROM work_items WHERE id = %s", (blocked_id,))
        if not blocker or not blocked:
            return

        blocker_uuid = self.graph.ensure_work_item(pg_id=blocker["id"], project_id=blocker["project_id"])
        blocked_uuid = self.graph.ensure_work_item(pg_id=blocked["id"], project_id=blocked["project_id"])
        self.graph.add_work_item_blocks_edge(blocker_uuid=blocker_uuid, blocked_uuid=blocked_uuid)

    def _wi_unblocked(self, event: dict) -> None:
        """Remove BLOCKS edge between two work items."""
        payload = event["payload"]
        blocker_id = payload.get("blocker_id")
        blocked_id = payload.get("blocked_id")
        if not blocker_id or not blocked_id:
            return

        blocker = self.db.execute_one("SELECT id, project_id FROM work_items WHERE id = %s", (blocker_id,))
        blocked = self.db.execute_one("SELECT id, project_id FROM work_items WHERE id = %s", (blocked_id,))
        if not blocker or not blocked:
            return

        blocker_uuid = self.graph.ensure_work_item(pg_id=blocker["id"], project_id=blocker["project_id"])
        blocked_uuid = self.graph.ensure_work_item(pg_id=blocked["id"], project_id=blocked["project_id"])
        self.graph.remove_work_item_blocks_edge(blocker_uuid=blocker_uuid, blocked_uuid=blocked_uuid)

    def _wi_memories_linked(self, event: dict) -> None:
        """Create LINKED_TO edges between a work item and memory statements."""
        payload = event["payload"]
        wi_id = event.get("work_item_id") or payload.get("work_item_id")
        memory_ids = payload.get("memory_ids", [])
        if not wi_id or not memory_ids:
            return

        row = self.db.execute_one("SELECT id, project_id FROM work_items WHERE id = %s", (wi_id,))
        if not row:
            return

        wi_uuid = self.graph.ensure_work_item(pg_id=row["id"], project_id=row["project_id"])
        for mid in memory_ids:
            try:
                self.graph.link_work_item_to_memory(wi_uuid, mid)
            except Exception:
                logger.debug("GraphProjection: failed to link work_item to memory %d", mid, exc_info=True)

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def _task_ensure(self, event: dict) -> None:
        """Ensure task node exists and matches PG state."""
        payload = event["payload"]
        task_id = payload.get("task_id")
        if not task_id:
            return

        row = self.db.execute_one("SELECT * FROM tasks WHERE id = %s", (task_id,))
        if not row:
            return

        graph_uuid = self.graph.ensure_task(
            pg_id=row["id"],
            project_id=row["project_id"],
            description=row.get("description") or "",
            status="completed" if row.get("completed_at") else "pending",
            completed_at=row["completed_at"].isoformat() if row.get("completed_at") else None,
        )

        if not row.get("graph_uuid"):
            self.db.execute(
                "UPDATE tasks SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                (graph_uuid, row["id"]),
            )
            self.db.commit()

    def _task_memories_linked(self, event: dict) -> None:
        """Create LINKED_TO edges between a task and memory statements."""
        payload = event["payload"]
        task_id = payload.get("task_id")
        memory_ids = payload.get("memory_ids", [])
        if not task_id or not memory_ids:
            return

        row = self.db.execute_one("SELECT id, project_id FROM tasks WHERE id = %s", (task_id,))
        if not row:
            return

        task_uuid = self.graph.ensure_task(pg_id=row["id"], project_id=row["project_id"])
        for mid in memory_ids:
            try:
                self.graph.link_task_to_memory(task_uuid, mid)
            except Exception:
                logger.debug("GraphProjection: failed to link task to memory %d", mid, exc_info=True)

    # ------------------------------------------------------------------
    # Thinking sequences
    # ------------------------------------------------------------------

    def _thinking_ensure(self, event: dict) -> None:
        """Ensure thinking sequence node exists and matches PG state."""
        payload = event["payload"]
        seq_id = payload.get("sequence_id")
        if not seq_id:
            return

        row = self.db.execute_one("SELECT * FROM thinking_sequences WHERE id = %s", (seq_id,))
        if not row:
            return

        graph_uuid = self.graph.ensure_thinking_sequence(
            pg_id=row["id"],
            project_id=row["project_id"],
            goal=row.get("goal") or "",
            status=row["status"],
            completed_at=row["completed_at"].isoformat() if row.get("completed_at") else None,
        )

        if not row.get("graph_uuid"):
            self.db.execute(
                "UPDATE thinking_sequences SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                (graph_uuid, row["id"]),
            )
            self.db.commit()

    def _thought_ensure(self, event: dict) -> None:
        """Ensure thought node exists and is linked to its sequence."""
        payload = event["payload"]
        thought_id = payload.get("thought_id")
        seq_id = payload.get("sequence_id")
        if not thought_id or not seq_id:
            return

        row = self.db.execute_one("SELECT * FROM thoughts WHERE id = %s", (thought_id,))
        if not row:
            return

        graph_uuid = self.graph.ensure_thought(
            pg_id=row["id"],
            sequence_pg_id=seq_id,
            thought_type=row.get("thought_type") or "general",
            content=row.get("content") or "",
        )

        if not row.get("graph_uuid"):
            self.db.execute(
                "UPDATE thoughts SET graph_uuid = %s, graph_synced = true WHERE id = %s",
                (graph_uuid, row["id"]),
            )
            self.db.commit()
