"""Hybrid search with Reciprocal Rank Fusion (RRF).

Up to six signals combined (dynamic weight selection):
  - Vector similarity (pgvector cosine distance)
  - Keyword matching (PostgreSQL full-text search)
  - Recency (updated_at DESC — newer memories rank higher)
  - Tag matching (array overlap)
  - Entity matching (entities TEXT[] overlap) — when entities are populated
  - Spreading activation (graph-based) — when activation engine is enabled

RRF formula: score = weight * (1 / (k + rank))

Design notes:
  - k=60 follows the original RRF paper (Cormack et al. 2009) and is standard
    in the literature. Not tuned for this specific use case. Smaller k would
    increase rank differentiation on small corpora; worth ablation testing.
  - Weights (0.50 / 0.20 / 0.20 / 0.10) give vector the largest share because
    embedding similarity is the strongest signal for semantic memory retrieval.
    Recency is a proper RRF participant — it competes fairly through the same
    fusion formula. No explicit decay function needed; RRF's 1/(k+rank)
    provides natural diminishing returns. Keyword and tag signals compensate
    for embedding blind spots (exact terms, categorical matches).
  - Recency uses updated_at (not created_at) so that corrected or refreshed
    memories surface as recent.
  - Candidate pool is limit * 5 per signal. On small corpora this examines a
    large fraction of total memories, which inflates recall metrics. At scale
    this is a reasonable efficiency tradeoff.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.analytics import track_operation
from cairn.core.constants import (
    CONTRADICTION_PENALTY,
    QUERY_TYPE_AFFINITY,
    RRF_WEIGHTS_DEFAULT,
    RRF_WEIGHTS_WITH_ACTIVATION,
    RRF_WEIGHTS_WITH_ENTITIES,
    TYPE_ROUTING_BOOST,
)
from cairn.core.mca import MCA_POOL_MULTIPLIER, MCAGate
from cairn.embedding.interface import EmbeddingInterface
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.config import LLMCapabilities
    from cairn.core.activation import ActivationEngine
    from cairn.core.reranker import Reranker
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

# RRF constant — higher k means rank differences matter less.
# k=60 is the standard from Cormack et al. 2009. Not ablation-tested here.
RRF_K = 60

# Default signal weights. Rebalanced in v0.23.0 to include recency.
# See module docstring for rationale and known limitations.
DEFAULT_WEIGHTS = {
    "vector": 0.50,
    "recency": 0.20,
    "keyword": 0.20,
    "tag": 0.10,
}


class SearchEngine:
    """Hybrid search over memories."""

    def __init__(
        self, db: Database, embedding: EmbeddingInterface, *,
        llm: LLMInterface | None = None,
        capabilities: LLMCapabilities | None = None,
        reranker: Reranker | None = None,
        rerank_candidates: int = 50,
        activation_engine: ActivationEngine | None = None,
    ):
        self.db = db
        self.embedding = embedding
        self.llm = llm
        self.capabilities = capabilities
        self.reranker = reranker
        self.rerank_candidates = rerank_candidates
        self.activation_engine = activation_engine
        self._mca_gate: MCAGate | None = None
        if capabilities is not None and capabilities.mca_gate:
            self._mca_gate = MCAGate()
            logger.info("MCA gate enabled (threshold=%.2f)", self._mca_gate.threshold)

    @track_operation("search")
    def search(
        self,
        query: str,
        project: str | list[str] | None = None,
        memory_type: str | list[str] | None = None,
        search_mode: str = "semantic",
        limit: int = 10,
        include_full: bool = False,
    ) -> list[dict]:
        """Search memories using hybrid RRF.

        Args:
            query: Natural language search query.
            project: Filter to project(s). String or list of strings.
            memory_type: Filter to memory type(s). String or list of strings.
            search_mode: "semantic" (hybrid), "keyword", or "vector".
            limit: Max results to return.
            include_full: If True, return full content. If False, return summary/truncated.

        Returns:
            List of memory dicts with relevance scores.
        """
        # Query expansion: enrich query for vector search only.
        # Keyword and tag signals use the original query to avoid
        # world-knowledge poisoning (e.g. "Caroline" expanding to
        # "Caroline Kennedy" when the corpus has a different Caroline).
        expanded = self._expand_query(query)

        if search_mode == "keyword":
            return self._keyword_search(query, project, memory_type, limit, include_full)
        elif search_mode == "vector":
            return self._vector_search(expanded, project, memory_type, limit, include_full)
        else:
            return self._hybrid_search(query, expanded, project, memory_type, limit, include_full)

    def _expand_query(self, query: str) -> str:
        """Expand search query with related terms via LLM.

        Returns the original query unchanged if LLM is unavailable, flag is off, or call fails.
        """
        can_expand = (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.query_expansion
        )
        if not can_expand:
            return query

        try:
            from cairn.llm.prompts import build_query_expansion_messages
            messages = build_query_expansion_messages(query)
            expanded = self.llm.generate(messages, max_tokens=256)
            if expanded and expanded.strip():
                logger.debug("Query expanded: %r -> %r", query, expanded.strip())
                return expanded.strip()
        except Exception:
            logger.warning("Query expansion failed, using original query", exc_info=True)

        return query

    def _build_filters(self, project: str | list[str] | None, memory_type: str | list[str] | None) -> tuple[str, list]:
        """Build WHERE clause fragments for common filters."""
        clauses = ["m.is_active = true"]
        params = []

        if project:
            if isinstance(project, list):
                clauses.append("p.name = ANY(%s)")
                params.append(project)
            else:
                clauses.append("p.name = %s")
                params.append(project)

        if memory_type:
            if isinstance(memory_type, list):
                clauses.append("m.memory_type = ANY(%s)")
                params.append(memory_type)
            else:
                clauses.append("m.memory_type = %s")
                params.append(memory_type)

        return " AND ".join(clauses), params

    def _vector_search(
        self, query: str, project: str | None, memory_type: str | None,
        limit: int, include_full: bool,
    ) -> list[dict]:
        """Pure vector similarity search."""
        query_vector = self.embedding.embed(query)
        where, params = self._build_filters(project, memory_type)

        # pgvector cosine distance: <=> returns distance (0 = identical)
        # We convert to similarity: 1 - distance
        rows = self.db.execute(
            f"""
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.created_at,
                   p.name as project,
                   1 - (m.embedding <=> %s::vector) as score
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where}
                AND m.embedding IS NOT NULL
            ORDER BY m.embedding <=> %s::vector
            LIMIT %s
            """,
            [str(query_vector)] + params + [str(query_vector), limit],
        )

        # Apply contradiction penalty and re-sort
        scored = {r["id"]: r["score"] for r in rows}
        penalized = self._apply_contradiction_penalty(scored)
        for r in rows:
            r["score"] = penalized[r["id"]]
        rows.sort(key=lambda r: r["score"], reverse=True)

        return self._format_results(rows, include_full)

    def _keyword_search(
        self, query: str, project: str | None, memory_type: str | None,
        limit: int, include_full: bool,
    ) -> list[dict]:
        """PostgreSQL full-text search."""
        where, params = self._build_filters(project, memory_type)

        rows = self.db.execute(
            f"""
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.created_at,
                   p.name as project,
                   ts_rank(to_tsvector('english', m.content), plainto_tsquery('english', %s)) as score
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where}
                AND to_tsvector('english', m.content) @@ plainto_tsquery('english', %s)
            ORDER BY score DESC
            LIMIT %s
            """,
            [query] + params + [query, limit],
        )

        # Apply contradiction penalty and re-sort
        scored = {r["id"]: r["score"] for r in rows}
        penalized = self._apply_contradiction_penalty(scored)
        for r in rows:
            r["score"] = penalized[r["id"]]
        rows.sort(key=lambda r: r["score"], reverse=True)

        return self._format_results(rows, include_full)

    def _hybrid_search(
        self, query: str, expanded: str, project: str | None, memory_type: str | None,
        limit: int, include_full: bool,
    ) -> list[dict]:
        """Hybrid search: vector + keyword + tag, fused via RRF.

        Uses expanded query for vector signal (robust to semantic noise)
        and original query for keyword/tag signals (precision-sensitive).
        """
        # Vector signal uses the expanded query for richer semantic matching
        query_vector = self.embedding.embed(expanded)
        where, params = self._build_filters(project, memory_type)

        # When reranking is enabled, widen the RRF pool to give the cross-encoder
        # more candidates to pick from. The reranker narrows back to `limit`.
        use_reranker = (
            self.reranker is not None
            and self.capabilities is not None
            and self.capabilities.reranking
        )
        use_mca = self._mca_gate is not None

        effective_limit = self.rerank_candidates if use_reranker else limit
        # MCA filters aggressively — widen pool so enough candidates survive
        if use_mca:
            effective_limit *= MCA_POOL_MULTIPLIER

        # Fetch a generous candidate set from each signal
        candidate_limit = effective_limit * 5

        # Signal 1: Vector search (uses expanded query embedding)
        vector_rows = self.db.execute(
            f"""
            SELECT m.id,
                   ROW_NUMBER() OVER (ORDER BY m.embedding <=> %s::vector) as rank
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where} AND m.embedding IS NOT NULL
            ORDER BY m.embedding <=> %s::vector
            LIMIT %s
            """,
            [str(query_vector)] + params + [str(query_vector), candidate_limit],
        )
        vector_ranks = {r["id"]: r["rank"] for r in vector_rows}

        # Signal 2: Keyword search (uses ORIGINAL query — exact terms matter)
        keyword_rows = self.db.execute(
            f"""
            SELECT m.id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank(to_tsvector('english', m.content),
                                        plainto_tsquery('english', %s)) DESC
                   ) as rank
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where}
                AND to_tsvector('english', m.content) @@ plainto_tsquery('english', %s)
            LIMIT %s
            """,
            [query] + params + [query, candidate_limit],
        )
        keyword_ranks = {r["id"]: r["rank"] for r in keyword_rows}

        # Signal 3: Recency (newer memories ranked higher by updated_at)
        recency_rows = self.db.execute(
            f"""
            SELECT m.id,
                   ROW_NUMBER() OVER (ORDER BY m.updated_at DESC) as rank
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where}
            LIMIT %s
            """,
            params + [candidate_limit],
        )
        recency_ranks = {r["id"]: r["rank"] for r in recency_rows}

        # Signal 4: Tag search (uses ORIGINAL query words — precision matters)
        query_words = [w.lower() for w in query.split() if len(w) > 2]
        tag_ranks = {}
        if query_words:
            tag_rows = self.db.execute(
                f"""
                SELECT m.id,
                       ROW_NUMBER() OVER (
                           ORDER BY (
                               SELECT COUNT(*) FROM unnest(m.tags || m.auto_tags) t
                               WHERE t ILIKE ANY(%s)
                           ) DESC
                       ) as rank
                FROM memories m
                LEFT JOIN projects p ON m.project_id = p.id
                WHERE {where}
                    AND (m.tags || m.auto_tags) && %s
                LIMIT %s
                """,
                [
                    [f"%{w}%" for w in query_words],
                ] + params + [
                    query_words,
                    candidate_limit,
                ],
            )
            tag_ranks = {r["id"]: r["rank"] for r in tag_rows}

        # Signal 5: Entity search (uses ORIGINAL query words — entity names are precise)
        entity_ranks = {}
        if query_words:
            entity_patterns = [f"%{w}%" for w in query_words]
            try:
                entity_rows = self.db.execute(
                    f"""
                    SELECT m.id,
                           ROW_NUMBER() OVER (
                               ORDER BY (
                                   SELECT COUNT(*) FROM unnest(m.entities) e
                                   WHERE e ILIKE ANY(%s)
                               ) DESC
                           ) as rank
                    FROM memories m
                    LEFT JOIN projects p ON m.project_id = p.id
                    WHERE {where}
                        AND m.entities != '{{}}' AND EXISTS (
                            SELECT 1 FROM unnest(m.entities) e WHERE e ILIKE ANY(%s)
                        )
                    LIMIT %s
                    """,
                    [entity_patterns] + params + [entity_patterns, candidate_limit],
                )
                entity_ranks = {r["id"]: r["rank"] for r in entity_rows}
            except Exception:
                # Graceful: entities column may not exist yet (migration not applied)
                logger.debug("Entity signal skipped (column may not exist)", exc_info=True)

        # Signal 6: Spreading activation (graph-based retrieval)
        activation_ranks = {}
        use_activation = (
            self.activation_engine is not None
            and self.capabilities is not None
            and self.capabilities.spreading_activation
        )
        if use_activation:
            try:
                # Use vector + keyword anchors as activation seeds
                anchor_ids = list(set(list(vector_ranks.keys())[:10] + list(keyword_ranks.keys())[:5]))
                anchor_scores = {}
                for aid in anchor_ids:
                    # Normalize: rank-1 gets 1.0, lower ranks get less
                    if aid in vector_ranks:
                        anchor_scores[aid] = max(anchor_scores.get(aid, 0), 1.0 / vector_ranks[aid])
                    if aid in keyword_ranks:
                        anchor_scores[aid] = max(anchor_scores.get(aid, 0), 1.0 / keyword_ranks[aid])

                # Resolve project_id for graph scoping
                act_project_id = None
                if project and not isinstance(project, list):
                    proj_row = self.db.execute_one(
                        "SELECT id FROM projects WHERE name = %s", (project,)
                    )
                    if proj_row:
                        act_project_id = proj_row["id"]

                activations = self.activation_engine.activate(
                    anchor_ids, anchor_scores, project_id=act_project_id,
                )

                if activations:
                    # Convert activation values to ranks (sorted by activation desc)
                    sorted_acts = sorted(activations.items(), key=lambda x: x[1], reverse=True)
                    activation_ranks = {
                        nid: rank + 1 for rank, (nid, _) in enumerate(sorted_acts)
                    }
            except Exception:
                logger.debug("Spreading activation failed", exc_info=True)

        # Dynamic weight selection based on available signals
        if activation_ranks and entity_ranks:
            weights = RRF_WEIGHTS_WITH_ACTIVATION
        elif entity_ranks:
            weights = RRF_WEIGHTS_WITH_ENTITIES
        else:
            weights = RRF_WEIGHTS_DEFAULT

        # Fuse via RRF
        all_ids = (
            set(vector_ranks) | set(keyword_ranks) | set(recency_ranks)
            | set(tag_ranks) | set(entity_ranks) | set(activation_ranks)
        )
        if not all_ids:
            return []

        scored = {}
        score_components = {}
        for memory_id in all_ids:
            score = 0.0
            components = {k: 0.0 for k in weights}
            if memory_id in vector_ranks:
                components["vector"] = weights["vector"] * (1.0 / (RRF_K + vector_ranks[memory_id]))
                score += components["vector"]
            if "recency" in weights and memory_id in recency_ranks:
                components["recency"] = weights["recency"] * (1.0 / (RRF_K + recency_ranks[memory_id]))
                score += components["recency"]
            if memory_id in keyword_ranks:
                components["keyword"] = weights["keyword"] * (1.0 / (RRF_K + keyword_ranks[memory_id]))
                score += components["keyword"]
            if memory_id in tag_ranks:
                components["tag"] = weights["tag"] * (1.0 / (RRF_K + tag_ranks[memory_id]))
                score += components["tag"]
            if "entity" in weights and memory_id in entity_ranks:
                components["entity"] = weights["entity"] * (1.0 / (RRF_K + entity_ranks[memory_id]))
                score += components["entity"]
            if "activation" in weights and memory_id in activation_ranks:
                components["activation"] = weights["activation"] * (1.0 / (RRF_K + activation_ranks[memory_id]))
                score += components["activation"]
            scored[memory_id] = score
            score_components[memory_id] = components

        # Penalize contradicted memories before ranking
        scored = self._apply_contradiction_penalty(scored)

        # Type routing: classify query intent and boost matching memory types
        query_intent = self._classify_query_intent(query)
        if query_intent:
            # Lightweight fetch of memory types for scoring
            type_ids = list(scored.keys())
            type_placeholders = ",".join(["%s"] * len(type_ids))
            type_rows = self.db.execute(
                f"SELECT id, memory_type FROM memories WHERE id IN ({type_placeholders})",
                tuple(type_ids),
            )
            memory_types = {r["id"]: r["memory_type"] for r in type_rows}
            scored = self._apply_type_boost(scored, memory_types, query_intent)

        # Sort by fused score, take top N (or wider pool for MCA/reranking)
        top_ids = sorted(scored, key=scored.get, reverse=True)[:effective_limit]

        if not top_ids:
            return []

        # Fetch full details for top results
        placeholders = ",".join(["%s"] * len(top_ids))
        rows = self.db.execute(
            f"""
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.created_at,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE m.id IN ({placeholders})
            """,
            tuple(top_ids),
        )

        # Build ordered candidate list (shared by MCA gate and reranker)
        row_map = {r["id"]: r for r in rows}
        candidates = []
        for memory_id in top_ids:
            if memory_id in row_map:
                candidates.append({
                    "id": memory_id,
                    "content": row_map[memory_id]["content"],
                    "row": row_map[memory_id],
                    "rrf_score": scored[memory_id],
                    "score_components": score_components.get(memory_id, {}),
                })

        # MCA gate: filter by keyword coverage
        if use_mca:
            filtered, _mca_stats = self._mca_gate.filter(query, candidates)
            if filtered:
                candidates = filtered
            else:
                # MCA filtered everything — fall back to RRF order
                logger.debug("MCA filtered all candidates, falling back to RRF order")

        # Reranking: cross-encoder picks the best `limit` from the (possibly filtered) pool
        if use_reranker:
            try:
                reranked = self.reranker.rerank(query, candidates, limit=limit)
            except Exception:
                logger.warning("Reranking failed, falling back to MCA/RRF order", exc_info=True)
                reranked = candidates[:limit]

            results = []
            for c in reranked:
                r = c["row"]
                r["score"] = round(c["rrf_score"], 6)
                r["score_components"] = {
                    k: round(v, 6) for k, v in c.get("score_components", {}).items()
                }
                if "rerank_score" in c:
                    r["score_components"]["rerank"] = round(c["rerank_score"], 4)
                if "mca_coverage" in c:
                    r["score_components"]["mca_coverage"] = c["mca_coverage"]
                results.append(r)

            return self._format_results(results, include_full, prescored=True)

        # Standard path: RRF ordering (possibly MCA-filtered)
        results = []
        for c in candidates[:limit]:
            r = c["row"]
            r["score"] = round(c["rrf_score"], 6)
            r["score_components"] = {
                k: round(v, 6) for k, v in c.get("score_components", {}).items()
            }
            if "mca_coverage" in c:
                r["score_components"]["mca_coverage"] = c["mca_coverage"]
            results.append(r)

        return self._format_results(results, include_full, prescored=True)

    def _classify_query_intent(self, query: str) -> str | None:
        """Classify query intent for type-routed retrieval.

        Returns intent string (factual/temporal/procedural/exploratory/debug),
        or None if classification is off/fails.
        """
        can_classify = (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.type_routing
        )
        if not can_classify:
            return None

        try:
            from cairn.core.utils import extract_json
            from cairn.llm.prompts import build_query_classification_messages
            messages = build_query_classification_messages(query)
            raw = self.llm.generate(messages, max_tokens=64)
            data = extract_json(raw, json_type="object")
            if data and "intent" in data:
                intent = str(data["intent"]).lower()
                if intent in QUERY_TYPE_AFFINITY:
                    logger.debug("Query classified as: %s", intent)
                    return intent
        except Exception:
            logger.debug("Query classification failed", exc_info=True)

        return None

    def _apply_type_boost(
        self, scored: dict[int, float], memory_types: dict[int, str], intent: str,
    ) -> dict[int, float]:
        """Boost scores for memories whose type matches the query intent affinity.

        Args:
            scored: memory_id -> score mapping.
            memory_types: memory_id -> memory_type mapping.
            intent: Classified query intent.

        Returns updated scored dict.
        """
        affine_types = set(QUERY_TYPE_AFFINITY.get(intent, []))
        if not affine_types:
            return scored

        return {
            mid: score * TYPE_ROUTING_BOOST if memory_types.get(mid) in affine_types else score
            for mid, score in scored.items()
        }

    def _apply_contradiction_penalty(self, scored: dict[int, float]) -> dict[int, float]:
        """Penalize memories that have incoming contradiction relations.

        Memories with a 'contradicts' relation targeting them get their score
        multiplied by CONTRADICTION_PENALTY (0.5), meaning they need to be 2x
        more relevant to outrank their replacement.
        """
        if not scored:
            return scored

        all_ids = list(scored.keys())
        placeholders = ",".join(["%s"] * len(all_ids))
        rows = self.db.execute(
            f"""
            SELECT DISTINCT target_id
            FROM memory_relations
            WHERE target_id IN ({placeholders})
                AND relation = 'contradicts'
            """,
            tuple(all_ids),
        )

        contradicted = {r["target_id"] for r in rows}
        if not contradicted:
            return scored

        return {
            mid: score * CONTRADICTION_PENALTY if mid in contradicted else score
            for mid, score in scored.items()
        }

    def _format_results(
        self, rows: list[dict], include_full: bool, prescored: bool = False,
    ) -> list[dict]:
        """Format search results for output."""
        results = []
        for r in rows:
            content = r["content"]
            if not include_full and len(content) > 500:
                content = content[:500] + "..."

            result = {
                "id": r["id"],
                "content": content if include_full else None,
                "summary": r.get("summary") or (content[:200] + "..." if len(content) > 200 else content),
                "memory_type": r["memory_type"],
                "importance": r["importance"],
                "project": r["project"],
                "tags": r["tags"],
                "auto_tags": r.get("auto_tags", []),
                "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else r["created_at"],
                "score": r.get("score", 0.0) if prescored else r.get("score", 0.0),
            }
            if r.get("score_components"):
                result["score_components"] = r["score_components"]
            results.append(result)
        return results

    def assess_confidence(self, query: str, results: list[dict]) -> dict | None:
        """Assess whether search results actually answer the query.

        Returns confidence assessment dict, or None if gating is off/unavailable/fails.
        """
        can_gate = (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.confidence_gating
            and results
        )
        if not can_gate:
            return None

        try:
            from cairn.core.utils import extract_json
            from cairn.llm.prompts import build_confidence_gating_messages
            messages = build_confidence_gating_messages(query, results)
            raw = self.llm.generate(messages, max_tokens=512)
            assessment = extract_json(raw, json_type="object")
            if assessment and "confidence" in assessment:
                return assessment
        except Exception:
            logger.warning("Confidence gating failed", exc_info=True)

        return None
