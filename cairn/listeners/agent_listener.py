"""AgentListener — translates agent lifecycle events into work item activity.

Subscribes to agent.* events emitted by workspace backends (Claude Code,
Agent SDK) and records them as work item activity log entries.

Events handled:
- agent.completed: logs completion/error + updates work item status
- agent.heartbeat: logs heartbeat with state/note
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.core.work_items import WorkItemManager

logger = logging.getLogger(__name__)


class AgentListener:
    """Records agent lifecycle events as work item activity."""

    def __init__(self, work_item_manager: WorkItemManager):
        self.wim = work_item_manager

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe("agent.completed", "agent_lifecycle", self.handle)
        event_bus.subscribe("agent.heartbeat", "agent_lifecycle_hb", self.handle)

    def handle(self, event: dict) -> None:
        event_type = event.get("event_type", "")
        work_item_id = event.get("work_item_id")
        payload = event.get("payload", {})
        actor = event.get("actor", "agent")

        if not work_item_id:
            return

        try:
            if event_type == "agent.completed":
                self._handle_completed(work_item_id, actor, payload)
            elif event_type == "agent.heartbeat":
                self._handle_heartbeat(work_item_id, actor, payload)
        except Exception:
            logger.warning(
                "AgentListener: failed to process %s for work item %s",
                event_type, work_item_id, exc_info=True,
            )

    def _handle_completed(self, work_item_id: int, actor: str, payload: dict) -> None:
        is_error = payload.get("is_error", False)
        cost_usd = payload.get("cost_usd")
        session_id = payload.get("session_id", "")
        backend = payload.get("backend", "unknown")

        if is_error:
            content = f"Agent dispatch failed ({backend}, session {session_id})"
        else:
            content = f"Agent dispatch completed ({backend}, session {session_id})"
            if cost_usd is not None:
                content += f" — ${cost_usd:.4f}"

        self.wim._log_activity(
            work_item_id, actor, "completed" if not is_error else "note",
            content,
            {"session_id": session_id, "cost_usd": cost_usd, "is_error": is_error},
        )
        self.wim.db.commit()

    def _handle_heartbeat(self, work_item_id: int, actor: str, payload: dict) -> None:
        session_id = payload.get("session_id", "")
        state = payload.get("state")
        note = payload.get("note")

        # Only log heartbeats with meaningful content to avoid spam
        if not note and not state:
            return

        content = f"Agent heartbeat ({session_id})"
        if state:
            content += f" — {state}"
        if note:
            content += f": {note}"

        self.wim._log_activity(
            work_item_id, actor, "heartbeat", content,
            {"session_id": session_id, "state": state},
        )
        self.wim.db.commit()
