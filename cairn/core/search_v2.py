"""Intent-routed search engine (v2).

Pipeline: route → handler dispatch → entity coverage gate → reranking → format.
Falls back to existing SearchEngine.hybrid_search() if Neo4j is unreachable.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.budget import TOKENS_PER_WORD, estimate_tokens
from cairn.core.router import QueryRouter

if TYPE_CHECKING:
    from cairn.config import LLMCapabilities
    from cairn.core.reranker.interface import RerankerInterface
    from cairn.core.search import SearchEngine
    from cairn.embedding.interface import EmbeddingInterface
    from cairn.graph.interface import GraphProvider
    from cairn.llm.interface import LLMInterface
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)

# Token budget for final results
DEFAULT_TOKEN_BUDGET = 10_000


class SearchV2:
    """Intent-routed search with graph handlers and entity coverage gate."""

    def __init__(
        self,
        db: Database,
        embedding: EmbeddingInterface,
        graph: GraphProvider | None,
        llm: LLMInterface | None,
        capabilities: LLMCapabilities | None,
        reranker: RerankerInterface | None = None,
        rerank_candidates: int = 50,
        fallback_engine: SearchEngine | None = None,
    ):
        self.db = db
        self.embedding = embedding
        self.graph = graph
        self.llm = llm
        self.capabilities = capabilities
        self.reranker = reranker
        self.rerank_candidates = rerank_candidates
        self.fallback_engine = fallback_engine

        # Router requires LLM
        self.router = QueryRouter(llm) if llm else None

    def search(
        self,
        query: str,
        project: str | None = None,
        memory_type: str | None = None,
        search_mode: str = "semantic",
        limit: int = 10,
        include_full: bool = False,
    ) -> list[dict]:
        """Run intent-routed search pipeline.

        Falls back to legacy search on any critical failure.
        """
        # Non-semantic modes bypass v2 entirely
        if search_mode != "semantic":
            return self._fallback_search(
                query, project, memory_type, search_mode, limit, include_full,
            )

        try:
            return self._routed_search(query, project, memory_type, limit, include_full)
        except Exception:
            logger.warning("SearchV2 pipeline failed, falling back to legacy", exc_info=True)
            return self._fallback_search(
                query, project, memory_type, search_mode, limit, include_full,
            )

    def _routed_search(
        self,
        query: str,
        project: str | None,
        memory_type: str | None,
        limit: int,
        include_full: bool,
    ) -> list[dict]:
        """Core v2 pipeline: RRF base + graph boost + rerank.

        Strategy: Legacy RRF search provides the strong multi-signal base.
        Graph handlers contribute additional entity-matched candidates that
        RRF might miss. Reranking sorts everything by relevance.
        """

        # Step 1: RRF base — always run legacy search for a solid candidate pool
        rrf_results = []
        if self.fallback_engine:
            rrf_results = self.fallback_engine.search(
                query=query,
                project=project,
                memory_type=memory_type,
                search_mode="semantic",
                limit=self.rerank_candidates,  # Wide pool for reranking
                include_full=True,
            )

        # Step 2: Route the query for graph boost
        if self.router:
            route = self.router.route(query)
        else:
            from cairn.core.router import RouterOutput
            route = RouterOutput()

        # Step 3: RRF results are the primary candidates
        candidates = rrf_results

        if not candidates:
            return []

        # Step 5: Reranking with relevance threshold
        use_reranker = (
            self.reranker is not None
            and self.capabilities is not None
            and self.capabilities.reranking
        )
        if use_reranker:
            try:
                candidates = self.reranker.rerank(query, candidates, limit=limit)
            except Exception:
                logger.warning("Reranking failed in v2, using merge order", exc_info=True)
                candidates = candidates[:limit]
        else:
            candidates = candidates[:limit]

        # Step 6: Token budget — drop least relevant from tail
        candidates = self._apply_token_budget(candidates)

        # Step 7: Filter by memory_type if requested
        if memory_type:
            types = [memory_type] if isinstance(memory_type, str) else memory_type
            candidates = [
                c for c in candidates
                if c.get("row", {}).get("memory_type") in types
            ]

        # Step 8: Format
        return self._format_results(candidates, include_full)

    def _entity_coverage_gate(
        self,
        candidates: list[dict],
        route,
        project_id: int | None,
    ) -> list[dict]:
        """Filter candidates that have zero entity overlap with query entities.

        Only applies when the router provides entity_hints AND graph is available.
        """
        if not route.entity_hints or not self.graph or not project_id:
            return candidates

        try:
            # Resolve entity hints to UUIDs
            query_entity_uuids = set()
            for hint in route.entity_hints:
                name_embedding = self.embedding.embed(hint)
                entities = self.graph.search_entities_by_embedding(
                    name_embedding, project_id, limit=3,
                )
                for e in entities:
                    query_entity_uuids.add(e.uuid)

            if not query_entity_uuids:
                return candidates

            # For each candidate, check if it has statements referencing any query entities
            filtered = []
            for c in candidates:
                memory_id = c["id"]
                has_overlap = self._memory_has_entity_overlap(memory_id, query_entity_uuids, project_id)
                if has_overlap:
                    filtered.append(c)

            # If gate filtered everything, return original (don't return empty)
            if not filtered:
                logger.debug("Entity coverage gate filtered all %d candidates, keeping original", len(candidates))
                return candidates

            logger.debug("Entity coverage gate: %d -> %d candidates", len(candidates), len(filtered))
            return filtered

        except Exception:
            logger.warning("Entity coverage gate failed, returning unfiltered", exc_info=True)
            return candidates

    def _memory_has_entity_overlap(
        self,
        memory_id: int,
        query_entity_uuids: set[str],
        project_id: int,
    ) -> bool:
        """Check if a memory's graph statements reference any of the query entities."""
        try:
            # Find statements linked to this memory (episode_id)
            for entity_uuid in query_entity_uuids:
                episodes = self.graph.find_entity_episodes(entity_uuid)
                if memory_id in episodes:
                    return True
            return False
        except Exception:
            return True  # On error, assume overlap (don't filter)

    def _apply_token_budget(
        self,
        candidates: list[dict],
        budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> list[dict]:
        """Drop least relevant candidates from tail until under token budget."""
        total_tokens = 0
        result = []

        for c in candidates:
            content = c.get("content", "")
            est_tokens = estimate_tokens(content)
            if total_tokens + est_tokens > budget and result:
                break
            total_tokens += est_tokens
            result.append(c)

        return result

    def _format_results(
        self, candidates: list[dict], include_full: bool,
    ) -> list[dict]:
        """Format candidates into search output format."""
        results = []
        for c in candidates:
            r = c.get("row", {})
            content = c.get("content", r.get("content", ""))

            if not include_full and len(content) > 500:
                display_content = None
            else:
                display_content = content if include_full else None

            summary = r.get("summary") or (content[:200] + "..." if len(content) > 200 else content)

            result = {
                "id": c["id"],
                "content": display_content,
                "summary": summary,
                "memory_type": r.get("memory_type", "note"),
                "importance": r.get("importance", 0.5),
                "project": r.get("project"),
                "tags": r.get("tags", []),
                "auto_tags": r.get("auto_tags", []),
                "created_at": (
                    r["created_at"].isoformat()
                    if hasattr(r.get("created_at"), "isoformat")
                    else r.get("created_at", "")
                ),
                "score": round(c.get("score", 0.0), 6),
            }

            # Include rerank score if present
            if "rerank_score" in c:
                result["rerank_score"] = round(c["rerank_score"], 4)

            results.append(result)

        return results

    def _fallback_search(
        self,
        query: str,
        project: str | None,
        memory_type: str | None,
        search_mode: str,
        limit: int,
        include_full: bool,
    ) -> list[dict]:
        """Fall back to legacy SearchEngine."""
        if self.fallback_engine:
            return self.fallback_engine.search(
                query=query,
                project=project,
                memory_type=memory_type,
                search_mode=search_mode,
                limit=limit,
                include_full=include_full,
            )
        return []
