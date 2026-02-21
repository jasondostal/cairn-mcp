"""Memory access tracking listener — bumps access_count and last_accessed_at.

Subscribes to search.executed and memory.recalled events,
updating access stats on memories that were returned to the user.
Runs via EventDispatcher (background thread) — never blocks search/recall.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class MemoryAccessListener:
    """Tracks memory access via event bus events."""

    def __init__(self, db: Database):
        self.db = db

    def register(self, event_bus: EventBus) -> None:
        """Subscribe to access-related events."""
        event_bus.subscribe("search.executed", "memory_access_search", self.handle)
        event_bus.subscribe("memory.recalled", "memory_access_recall", self.handle)

    def handle(self, event: dict) -> None:
        """Bump access_count and last_accessed_at for accessed memories."""
        payload = event.get("payload") or {}
        memory_ids = payload.get("memory_ids", [])
        if not memory_ids:
            return

        try:
            placeholders = ",".join(["%s"] * len(memory_ids))
            self.db.execute(
                f"""
                UPDATE memories
                SET access_count = access_count + 1,
                    last_accessed_at = NOW()
                WHERE id IN ({placeholders})
                """,
                tuple(memory_ids),
            )
            self.db.commit()
            logger.debug(
                "MemoryAccess: bumped access for %d memories", len(memory_ids),
            )
        except Exception:
            logger.warning(
                "MemoryAccess: failed to update access counts", exc_info=True,
            )
            try:
                self.db.rollback()
            except Exception:
                pass
