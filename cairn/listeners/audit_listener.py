"""AuditListener — writes immutable audit_log entries for mutation events.

Subscribes to memory.*, work_item.*, task.*, and thinking.* events.
Extracts action and resource_type from event_type, passes trace_id
from the event record (not current_trace — runs in dispatcher thread).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.audit import AuditManager
    from cairn.core.event_bus import EventBus

logger = logging.getLogger(__name__)

# Event types that represent mutations worth auditing.
# Read-only events (search.executed, memory.recalled) are excluded.
_AUDITED_DOMAINS = {"memory", "work_item", "task", "thinking", "settings"}


class AuditListener:
    """Writes audit_log entries for all mutation events."""

    def __init__(self, audit_manager: AuditManager):
        self.audit = audit_manager

    def register(self, event_bus: EventBus) -> None:
        """Subscribe to mutation event domains."""
        event_bus.subscribe("memory.*", "audit_memory", self.handle)
        event_bus.subscribe("work_item.*", "audit_work_item", self.handle)
        event_bus.subscribe("task.*", "audit_task", self.handle)
        event_bus.subscribe("thinking.*", "audit_thinking", self.handle)
        event_bus.subscribe("settings.*", "audit_settings", self.handle)

    def handle(self, event: dict) -> None:
        """Route event to audit log."""
        event_type = event.get("event_type", "")
        parts = event_type.split(".", 1)
        if len(parts) != 2:
            return

        resource_type, action = parts
        if resource_type not in _AUDITED_DOMAINS:
            return

        payload = event.get("payload") or {}

        # Extract resource ID from payload (conventions vary by domain)
        resource_id = (
            payload.get("memory_id")
            or payload.get("work_item_id")
            or payload.get("task_id")
            or payload.get("sequence_id")
            or event.get("work_item_id")
        )

        actor = payload.get("actor")

        try:
            self.audit.log(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                project_id=event.get("project_id"),
                session_name=event.get("session_name"),
                trace_id=event.get("trace_id"),
                after_state=payload,
                **({"actor": actor} if actor else {}),
            )
        except Exception:
            logger.warning(
                "AuditListener: failed to log %s.%s resource=%s",
                resource_type, action, resource_id, exc_info=True,
            )
