"""Session synthesis listener — auto-summarize sessions on close.

Subscribes to session_end events. Calls SessionSynthesizer to generate
a narrative, then stores it as a session_summary memory.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.core.memory import MemoryStore
    from cairn.core.synthesis import SessionSynthesizer
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class SessionSynthesisListener:
    """Auto-synthesize sessions when they close."""

    def __init__(
        self,
        synthesizer: SessionSynthesizer,
        memory_store: MemoryStore,
        db: Database,
    ):
        self.synthesizer = synthesizer
        self.memory_store = memory_store
        self.db = db

    def register(self, event_bus: EventBus) -> None:
        """Subscribe to session_end events."""
        event_bus.subscribe("session_end", "session_synthesis", self.handle)

    def handle(self, event: dict) -> None:
        """Synthesize session and store as memory."""
        session_name = event.get("session_name")
        project_id = event.get("project_id")
        if not session_name or not project_id:
            logger.debug("SessionSynthesis: skipping — no session_name or project_id")
            return

        # Look up project name
        row = self.db.execute_one("SELECT name FROM projects WHERE id = %s", (project_id,))
        if not row:
            return
        project = row["name"]

        result = self.synthesizer.synthesize(project, session_name)
        narrative = result.get("narrative")
        memory_count = result.get("memory_count", 0)

        if not narrative or memory_count == 0:
            logger.debug(
                "SessionSynthesis: no narrative for session %s (%d memories)",
                session_name, memory_count,
            )
            return

        # Store the synthesis as a memory (enrich=False — it's already a summary)
        self.memory_store.store(
            content=narrative,
            project=project,
            memory_type="session_summary",
            importance=0.4,
            session_name=session_name,
            enrich=False,
            author="assistant",
        )
        logger.info(
            "SessionSynthesis: stored summary for session %s (%d memories)",
            session_name, memory_count,
        )
