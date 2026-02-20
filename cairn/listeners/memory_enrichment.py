"""Memory enrichment listener — async graph persist + relationship extraction.

Subscribes to memory.created events and runs the Phase 2 enrichment
that was previously inline in MemoryStore.store(). Gets retry logic
(5 attempts, exponential backoff) from the EventDispatcher for free.

For memory.inactivated events, could clean up Neo4j in the future.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.core.memory import MemoryStore

logger = logging.getLogger(__name__)


class MemoryEnrichmentListener:
    """Event-driven enrichment for memory operations."""

    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store

    def register(self, event_bus: EventBus) -> None:
        """Subscribe to memory events."""
        event_bus.subscribe("memory.*", "memory_enrichment", self.handle)

    def handle(self, event: dict) -> None:
        """Route event to the appropriate handler."""
        event_type = event["event_type"]
        if event_type == "memory.created":
            self._handle_created(event)
        elif event_type == "memory.inactivated":
            self._handle_inactivated(event)
        else:
            logger.debug("MemoryEnrichment: no handler for %s", event_type)

    def _handle_created(self, event: dict) -> None:
        """Run post-store enrichment (graph persist, relationships, edges)."""
        payload = event["payload"]
        memory_id = payload.get("memory_id")
        if not memory_id:
            logger.warning("MemoryEnrichment: memory.created missing memory_id")
            return

        project_id = payload.get("project_id")
        enrich = payload.get("enrich", True)
        memory_type = payload.get("memory_type", "note")

        # Reconstruct extraction_result if present
        extraction_result = None
        extraction_data = payload.get("extraction_result")
        if extraction_data:
            try:
                from cairn.core.extraction import ExtractionResult
                extraction_result = ExtractionResult(**extraction_data)
            except Exception:
                logger.warning(
                    "MemoryEnrichment: failed to reconstruct extraction result for memory #%d",
                    memory_id, exc_info=True,
                )

        # Fetch memory row for content, embedding, entities, session_name
        row = self.memory_store.db.execute_one(
            """
            SELECT content, embedding, session_name, entities,
                   p.name as project_name
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE m.id = %s
            """,
            (memory_id,),
        )
        if not row:
            logger.warning("MemoryEnrichment: memory #%d not found", memory_id)
            return

        self.memory_store._post_store_enrichment(
            memory_id=memory_id,
            project_id=project_id,
            extraction_result=extraction_result,
            enrich=enrich,
            content=row["content"],
            vector=row["embedding"],
            session_name=row["session_name"],
            entities=row.get("entities") or [],
            final_type=memory_type,
            project=row.get("project_name") or "",
        )

        logger.info("MemoryEnrichment: enrichment complete for memory #%d", memory_id)

    def _handle_inactivated(self, event: dict) -> None:
        """Handle memory inactivation — future: Neo4j statement cleanup."""
        # TODO: invalidate Neo4j statements for this episode_id
        pass
