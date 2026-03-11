"""Graph provider factory. Neo4j is required — fails hard if not available."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.graph.config import Neo4jConfig
    from cairn.graph.interface import GraphProvider

logger = logging.getLogger(__name__)


def get_graph_provider(config: Neo4jConfig | None = None) -> GraphProvider:
    """Create and return a Neo4j graph provider.

    Neo4j is a required dependency. Raises RuntimeError if initialization fails.
    """
    from cairn.graph.config import load_neo4j_config
    from cairn.graph.neo4j_provider import Neo4jGraphProvider

    cfg = config or load_neo4j_config()
    return Neo4jGraphProvider(cfg)
