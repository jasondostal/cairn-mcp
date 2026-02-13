"""Graph provider factory. Returns None when Neo4j is not configured (graceful degradation)."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.graph.config import Neo4jConfig
    from cairn.graph.interface import GraphProvider

logger = logging.getLogger(__name__)


def get_graph_provider(config: Neo4jConfig | None = None) -> GraphProvider | None:
    """Create and return a graph provider, or None if not configured.

    Checks CAIRN_GRAPH_BACKEND env var. Currently only 'neo4j' is supported.
    Returns None for any other value or if initialization fails.
    """
    backend = os.getenv("CAIRN_GRAPH_BACKEND", "").lower()
    if backend != "neo4j":
        return None

    try:
        from cairn.graph.config import load_neo4j_config
        from cairn.graph.neo4j_provider import Neo4jGraphProvider

        cfg = config or load_neo4j_config()
        provider = Neo4jGraphProvider(cfg)
        return provider
    except ImportError:
        logger.warning("neo4j package not installed — graph features disabled")
        return None
    except Exception:
        logger.warning("Failed to initialize Neo4j graph provider", exc_info=True)
        return None
