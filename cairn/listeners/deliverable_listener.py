"""DeliverableListener — auto-generates deliverables when work items complete.

Subscribes to work_item.completed events. Gathers activity log and linked
memories, synthesizes them into a structured deliverable via LLM (fast tier),
and creates the deliverable in pending_review status.

Falls back to a mechanical (no-LLM) deliverable if the LLM is unavailable.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.deliverables import DeliverableManager
    from cairn.core.event_bus import EventBus
    from cairn.core.work_items import WorkItemManager
    from cairn.llm.interface import LLMInterface
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)

_SYNTHESIS_PROMPT = """You are summarizing the work an AI agent did on a task. Given the task details and activity log below, produce a structured JSON deliverable.

TASK:
Title: {title}
Description: {description}

ACTIVITY LOG (most recent first):
{activity_log}

LINKED MEMORIES:
{linked_memories}

Produce a JSON object with exactly these fields:
- "summary": 1-3 sentence summary of what was accomplished
- "changes": list of objects with "description" (what changed) and "type" (file/memory/config/code/other)
- "decisions": list of objects with "decision" (what was decided) and "rationale" (why)
- "open_items": list of objects with "description" (what's left) and "priority" (high/medium/low)

Be concise. Focus on outcomes, not process. If nothing meaningful happened, say so.
Respond with ONLY the JSON object, no markdown fences."""


class DeliverableListener:
    """Auto-generates deliverables on work item completion."""

    def __init__(
        self,
        deliverable_manager: DeliverableManager,
        work_item_manager: WorkItemManager,
        db: Database,
        llm: LLMInterface | None = None,
    ):
        self.deliverable_manager = deliverable_manager
        self.work_item_manager = work_item_manager
        self.db = db
        self.llm = llm

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe("work_item.completed", "deliverable_auto_gen", self.handle)

    def handle(self, event: dict) -> None:
        payload = event.get("payload") or {}
        work_item_id = payload.get("work_item_id")
        if not work_item_id:
            logger.warning("DeliverableListener: work_item.completed missing work_item_id")
            return

        # Skip if deliverable already exists (manual creation)
        existing = self.deliverable_manager.get(work_item_id)
        if existing:
            logger.info(
                "DeliverableListener: deliverable already exists for work item #%d (v%d), skipping",
                work_item_id, existing["version"],
            )
            return

        try:
            self._generate(work_item_id)
        except Exception:
            logger.warning(
                "DeliverableListener: failed to generate deliverable for #%d",
                work_item_id, exc_info=True,
            )

    def _generate(self, work_item_id: int) -> None:
        """Gather context and generate a deliverable."""
        # Get work item details
        item = self.work_item_manager.get(work_item_id)
        if not item:
            logger.warning("DeliverableListener: work item #%d not found", work_item_id)
            return

        # Get activity log
        activity = self.work_item_manager.get_activity(work_item_id, limit=50)
        activities = activity.get("activities", [])

        # Get linked memories
        linked_memories = self._get_linked_memories(work_item_id)

        if self.llm:
            self._generate_with_llm(item, activities, linked_memories)
        else:
            self._generate_mechanical(item, activities, linked_memories)

    def _generate_with_llm(
        self, item: dict, activities: list[dict], linked_memories: list[dict]
    ) -> None:
        """Use LLM to synthesize a structured deliverable."""
        # Format activity log
        activity_lines = []
        for a in activities[:30]:  # cap to avoid token overflow
            line = f"- [{a.get('activity_type', '?')}] {a.get('content', '(no content)')}"
            if a.get("actor"):
                line += f" (by {a['actor']})"
            activity_lines.append(line)
        activity_text = "\n".join(activity_lines) if activity_lines else "(no activity recorded)"

        # Format linked memories
        memory_lines = []
        for m in linked_memories[:10]:
            memory_lines.append(f"- [{m.get('memory_type', 'note')}] {m.get('summary', m.get('content', '')[:200])}")
        memory_text = "\n".join(memory_lines) if memory_lines else "(no linked memories)"

        prompt = _SYNTHESIS_PROMPT.format(
            title=item.get("title", ""),
            description=item.get("description", "")[:2000],
            activity_log=activity_text,
            linked_memories=memory_text,
        )

        try:
            assert self.llm is not None
            response = self.llm.generate([{"role": "user", "content": prompt}], max_tokens=1000)
            parsed = json.loads(response)

            self.deliverable_manager.create(
                work_item_id=item["id"],
                summary=parsed.get("summary", ""),
                changes=parsed.get("changes", []),
                decisions=parsed.get("decisions", []),
                open_items=parsed.get("open_items", []),
                metrics=self._compute_metrics(activities),
                status="pending_review",
            )
            logger.info("DeliverableListener: LLM deliverable created for #%d", item["id"])

        except (json.JSONDecodeError, KeyError):
            logger.warning(
                "DeliverableListener: LLM returned invalid JSON for #%d, falling back to mechanical",
                item["id"], exc_info=True,
            )
            self._generate_mechanical(item, activities, linked_memories)

    def _generate_mechanical(
        self, item: dict, activities: list[dict], linked_memories: list[dict]
    ) -> None:
        """Generate a basic deliverable without LLM — structured but not synthesized."""
        # Build summary from activity types
        type_counts: dict[str, int] = {}
        for a in activities:
            t = a.get("activity_type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        summary_parts = [f"Completed '{item.get('title', 'untitled')}'."]
        if type_counts:
            counts_str = ", ".join(f"{v} {k}" for k, v in sorted(type_counts.items()))
            summary_parts.append(f"Activity: {counts_str}.")

        # Extract changes from heartbeat/checkpoint notes
        changes = []
        for a in activities:
            if a.get("activity_type") in ("checkpoint", "note") and a.get("content"):
                changes.append({"description": a["content"][:200], "type": "other"})

        self.deliverable_manager.create(
            work_item_id=item["id"],
            summary=" ".join(summary_parts),
            changes=changes[:20],
            decisions=[],
            open_items=[],
            metrics=self._compute_metrics(activities),
            status="pending_review",
        )
        logger.info("DeliverableListener: mechanical deliverable created for #%d", item["id"])

    def _get_linked_memories(self, work_item_id: int) -> list[dict]:
        """Fetch memories linked to a work item."""
        rows = self.db.execute(
            """
            SELECT m.id, m.content, m.memory_type, m.importance,
                   COALESCE(m.summary, LEFT(m.content, 200)) AS summary
            FROM work_item_memory_links wml
            JOIN memories m ON wml.memory_id = m.id
            WHERE wml.work_item_id = %s AND m.is_active = true
            ORDER BY m.importance DESC
            LIMIT 20
            """,
            (work_item_id,),
        )
        return [dict(r) for r in rows]

    def _compute_metrics(self, activities: list[dict]) -> dict:
        """Compute basic metrics from activity log."""
        heartbeats = [a for a in activities if a.get("activity_type") == "heartbeat"]
        checkpoints = [a for a in activities if a.get("activity_type") == "checkpoint"]
        return {
            "total_activities": len(activities),
            "heartbeat_count": len(heartbeats),
            "checkpoint_count": len(checkpoints),
        }
