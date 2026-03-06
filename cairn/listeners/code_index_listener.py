"""Code index listener — event-driven re-indexing of changed files.

Subscribes to ``code.file_changed`` events and re-indexes individual
files when they change. Follows the GraphProjectionListener pattern.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.event_bus import EventBus
    from cairn.graph.interface import GraphProvider
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class CodeIndexListener:
    """Re-index individual files when code.file_changed events fire."""

    def __init__(self, graph: GraphProvider, db: Database):
        self.graph = graph
        self.db = db

    def register(self, event_bus: EventBus) -> None:
        """Subscribe to code file change events."""
        event_bus.subscribe("code.file_changed", "code_reindex", self.handle)

    def handle(self, event: dict) -> None:
        """Re-index a single file that has changed."""
        payload = event.get("payload", {})
        file_path = payload.get("file_path")
        project = payload.get("project")
        if not file_path or not project:
            logger.debug("CodeIndexListener: missing file_path or project in event")
            return

        try:
            from cairn.code.indexer import CodeIndexer
            from cairn.code.parser import CodeParser
            from cairn.core.utils import get_or_create_project

            project_id = get_or_create_project(self.db, project)
            parser = CodeParser()
            indexer = CodeIndexer(parser, self.graph)
            result = indexer.index_file(
                Path(file_path), project=project, project_id=project_id
            )
            if result.errors:
                logger.warning("CodeIndexListener: errors re-indexing %s: %s", file_path, result.errors)
            elif result.files_indexed:
                logger.info("CodeIndexListener: re-indexed %s (%d symbols)", file_path, result.symbols_created)
        except Exception:
            logger.warning("CodeIndexListener: failed to re-index %s", file_path, exc_info=True)
