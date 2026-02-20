"""Unified search engine — graph-primary retrieval.

Always instantiated as the single search entry point. Two modes:

- **Passthrough** (capabilities.search_v2=false): Delegates directly to
  SearchEngine (RRF hybrid search). Zero overhead.
- **Enhanced** (capabilities.search_v2=true): Graph-primary retrieval.
  Extracts entities from query via embedding, traverses Neo4j graph for
  entity-anchored results, uses RRF as backfill. Reranking + token budget.

Graceful degradation chain:
  Graph retrieval → SearchEngine (RRF) → vector-only → empty results.

On any failure in the enhanced pipeline, falls back to SearchEngine
transparently. The caller never needs to know which path executed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.budget import estimate_tokens
from cairn.core.handlers import HANDLERS, SearchContext, _blend_results, _fetch_memories_by_ids
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

# Token budget for final results (enhanced mode only)
DEFAULT_TOKEN_BUDGET = 10_000


class SearchV2:
    """Unified search engine — single entry point for all search operations.

    Wraps SearchEngine and optionally adds enhanced pipeline features
    (intent routing, entity coverage gate, reranking, token budgets)
    when capabilities.search_v2 is enabled.
    """

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

        # Enhanced mode: intent routing + entity coverage + token budgets
        self.enhanced = (
            capabilities is not None
            and capabilities.search_v2
        )

        # Router requires LLM (only initialized in enhanced mode)
        self.router = QueryRouter(llm) if (llm and self.enhanced) else None

    def search(
        self,
        query: str,
        project: str | list[str] | None = None,
        memory_type: str | list[str] | None = None,
        search_mode: str = "semantic",
        limit: int = 10,
        include_full: bool = False,
    ) -> list[dict]:
        """Search memories.

        In passthrough mode, delegates directly to SearchEngine.
        In enhanced mode, runs the intent-routed pipeline with
        fallback to SearchEngine on any failure.
        """
        # Passthrough mode: delegate directly to SearchEngine
        if not self.enhanced:
            return self._fallback_search(
                query, project, memory_type, search_mode, limit, include_full,
            )

        # Enhanced mode: non-semantic modes bypass the v2 pipeline
        if search_mode != "semantic":
            return self._fallback_search(
                query, project, memory_type, search_mode, limit, include_full,
            )

        try:
            return self._routed_search(query, project, memory_type, limit, include_full)
        except Exception:
            logger.warning("Enhanced search pipeline failed, falling back to RRF", exc_info=True)
            return self._fallback_search(
                query, project, memory_type, search_mode, limit, include_full,
            )

    def assess_confidence(self, query: str, results: list[dict]) -> dict | None:
        """Passthrough to SearchEngine's confidence assessment."""
        if self.fallback_engine:
            return self.fallback_engine.assess_confidence(query, results)
        return None

    # Minimum cosine similarity for entity extraction from queries.
    # Without this, every word matches random entities (Bug 1, LoCoMo diagnostic).
    ENTITY_EXTRACTION_THRESHOLD = 0.7

    def _extract_query_entities(self, query: str, project_id: int) -> list:
        """Extract entities from query using Core-style chunk+embed approach.

        Chunks query into words, bigrams, and full query. Embeds each chunk
        and finds matching entities in Neo4j via vector similarity. No LLM call.

        Uses ENTITY_EXTRACTION_THRESHOLD to filter garbage matches.
        """
        if not self.graph:
            return []

        words = query.lower().split()
        # Build chunks: individual words (3+ chars), bigrams, full query
        chunks = {w for w in words if len(w) >= 3}
        for i in range(len(words) - 1):
            chunks.add(f"{words[i]} {words[i+1]}")
        chunks.add(query)

        entities = {}
        for chunk in chunks:
            try:
                embedding = self.embedding.embed(chunk)
                matches = self.graph.search_entities_by_embedding(
                    embedding, project_id, limit=3,
                    threshold=self.ENTITY_EXTRACTION_THRESHOLD,
                )
                for entity in matches:
                    if entity.uuid not in entities:
                        entities[entity.uuid] = entity
            except Exception:
                logger.debug("Entity extraction failed for chunk '%s'", chunk, exc_info=True)

        logger.debug(
            "Query entity extraction: %d chunks → %d entities (threshold=%.2f)",
            len(chunks), len(entities), self.ENTITY_EXTRACTION_THRESHOLD,
        )
        return list(entities.values())

    def _routed_search(
        self,
        query: str,
        project: str | list[str] | None,
        memory_type: str | list[str] | None,
        limit: int,
        include_full: bool,
    ) -> list[dict]:
        """Graph-primary search pipeline.

        Strategy: Extract entities from query → graph traversal as PRIMARY
        retrieval → RRF as backfill when graph returns insufficient results.
        Reranking sorts by cross-encoder relevance. Token budget trims tail.
        """
        project_id = self._resolve_project_id(project) if project else None

        # Step 1: Extract entities from query (no LLM, just embedding + Neo4j)
        query_entities = []
        if self.graph and project_id:
            try:
                query_entities = self._extract_query_entities(query, project_id)
            except Exception:
                logger.warning("Query entity extraction failed", exc_info=True)

        # Step 2: Graph-primary path if entities found
        candidates = []
        if query_entities and self.graph:
            try:
                # Build a synthetic route with the extracted entity hints
                from cairn.core.router import RouterOutput
                entity_route = RouterOutput(
                    query_type="entity_lookup",
                    entity_hints=[e.name for e in query_entities],
                    confidence=1.0,  # We found real entities, not guessing
                )

                ctx = SearchContext(
                    query=query, route=entity_route, project_id=project_id,
                    project_name=project if isinstance(project, str) else None,
                    db=self.db, embedding=self.embedding, graph=self.graph,
                    limit=limit,
                    resolved_entities=query_entities,
                )

                # Entity lookup is the primary graph handler
                handler = HANDLERS.get("entity_lookup")
                if handler:
                    candidates = handler(ctx)
                    logger.debug(
                        "Graph-primary: entity_lookup returned %d results",
                        len(candidates),
                    )
            except Exception:
                logger.warning("Graph-primary search failed", exc_info=True)
                candidates = []

        # Step 3: RRF backfill — always run, blend with graph results
        rrf_results = []
        if self.fallback_engine:
            rrf_results = self.fallback_engine.search(
                query=query,
                project=project,
                memory_type=memory_type,
                search_mode="semantic",
                limit=self.rerank_candidates,
                include_full=True,
            )

        if candidates:
            # Graph is primary, RRF backfills
            candidates = _blend_results(candidates, rrf_results, limit * 3)
        elif rrf_results:
            # No graph results — try router-based handlers as supplement
            candidates = rrf_results
            try:
                if self.router and self.graph and project_id:
                    route = self.router.route(query)
                    if route.query_type in {"temporal", "exploratory"}:
                        ctx = SearchContext(
                            query=query, route=route, project_id=project_id,
                            project_name=project if isinstance(project, str) else None,
                            db=self.db, embedding=self.embedding, graph=self.graph,
                            limit=limit,
                        )
                        handler = HANDLERS.get(route.query_type)
                        if handler:
                            handler_results = handler(ctx)
                            if handler_results:
                                candidates = _blend_results(rrf_results, handler_results, limit * 3)
            except Exception:
                logger.debug("Supplementary handler dispatch failed", exc_info=True)

        if not candidates:
            return []

        # Step 4: Reranking
        use_reranker = (
            self.reranker is not None
            and self.capabilities is not None
            and self.capabilities.reranking
        )
        if use_reranker:
            try:
                candidates = self.reranker.rerank(query, candidates, limit=limit)
            except Exception:
                logger.warning("Reranking failed, using current order", exc_info=True)
                candidates = candidates[:limit]
        else:
            candidates = candidates[:limit]

        # Step 5: Token budget — drop least relevant from tail
        candidates = self._apply_token_budget(candidates)

        # Step 6: Filter by memory_type if requested
        if memory_type:
            types = [memory_type] if isinstance(memory_type, str) else memory_type
            candidates = [
                c for c in candidates
                if c.get("row", {}).get("memory_type") in types
            ]

        # Step 7: Format
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

            filtered = []
            for c in candidates:
                memory_id = c["id"]
                has_overlap = self._memory_has_entity_overlap(memory_id, query_entity_uuids, project_id)
                if has_overlap:
                    filtered.append(c)

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

            if "rerank_score" in c:
                result["rerank_score"] = round(c["rerank_score"], 4)

            results.append(result)

        return results

    def _resolve_project_id(self, project: str | list[str] | None) -> int | None:
        """Resolve project name to ID for SearchContext."""
        if not project or not isinstance(project, str):
            return None
        try:
            from cairn.core.utils import get_project
            return get_project(self.db, project)
        except Exception:
            return None

    def _fallback_search(
        self,
        query: str,
        project: str | list[str] | None,
        memory_type: str | list[str] | None,
        search_mode: str,
        limit: int,
        include_full: bool,
    ) -> list[dict]:
        """Delegate to SearchEngine (RRF hybrid search)."""
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
