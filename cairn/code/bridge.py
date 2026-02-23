"""Knowledge-code bridging via REFERENCED_IN edges.

Creates REFERENCED_IN edges between Entity nodes and CodeSymbol/CodeFile nodes
using name matching. Two tiers:

- Tier 1 — Symbol name match: toLower(Entity.name) = toLower(CodeSymbol.name)
- Tier 2 — File path match: Entity.name contains '.' AND CodeFile.path ends with Entity.name

All operations use MERGE (idempotent). Non-blocking, best-effort.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.graph.interface import GraphProvider

logger = logging.getLogger(__name__)


class CodeBridgeService:
    """Bridges knowledge entities to code graph nodes."""

    def __init__(self, graph: GraphProvider):
        self.graph = graph

    def bridge_all(self, project_id: int) -> dict:
        """Batch bridge all entities to all code in the project.

        Used after code_index to create REFERENCED_IN edges for the
        entire project's entity ↔ code overlap.

        Returns dict with edge counts per tier.
        """
        symbol_edges = self.graph.bridge_entities_to_symbols_batch(project_id)
        file_edges = self.graph.bridge_entities_to_files_batch(project_id)

        total = symbol_edges + file_edges
        logger.info(
            "Code bridge (batch): %d symbol edges, %d file edges",
            symbol_edges, file_edges,
        )
        return {
            "symbol_edges": symbol_edges,
            "file_edges": file_edges,
            "total": total,
        }

    def bridge_entity_names(self, names: list[str], project_id: int) -> dict:
        """Bridge specific entity names to matching code nodes.

        Used after memory enrichment to bridge newly created/merged
        entities without re-scanning the entire project.

        Returns dict with edge counts per tier.
        """
        if not names:
            return {"symbol_edges": 0, "file_edges": 0, "total": 0}

        symbol_edges = self.graph.bridge_entity_names_to_symbols(names, project_id)
        file_edges = self.graph.bridge_entity_names_to_files(names, project_id)

        total = symbol_edges + file_edges
        if total > 0:
            logger.info(
                "Code bridge (targeted, %d names): %d symbol edges, %d file edges",
                len(names), symbol_edges, file_edges,
            )
        return {
            "symbol_edges": symbol_edges,
            "file_edges": file_edges,
            "total": total,
        }
