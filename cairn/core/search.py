"""Hybrid search with Reciprocal Rank Fusion (RRF).

Three signals combined:
  - Vector similarity (pgvector cosine distance)
  - Keyword matching (PostgreSQL full-text search)
  - Tag matching (array overlap)

RRF formula: score = weight * (1 / (k + rank))

Design notes:
  - k=60 follows the original RRF paper (Cormack et al. 2009) and is standard
    in the literature. Not tuned for this specific use case. Smaller k would
    increase rank differentiation on small corpora; worth ablation testing.
  - Weights (0.60 / 0.25 / 0.15) are based on initial tuning against the
    eval benchmark. They are NOT the result of exhaustive grid search or
    ablation. Vector gets the most weight because embedding similarity is the
    strongest signal for semantic memory retrieval. Keyword and tag signals
    compensate for embedding blind spots (exact terms, categorical matches).
  - Candidate pool is limit * 5 per signal. On small corpora this examines a
    large fraction of total memories, which inflates recall metrics. At scale
    this is a reasonable efficiency tradeoff.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.core.constants import CONTRADICTION_PENALTY
from cairn.embedding.engine import EmbeddingEngine
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.config import LLMCapabilities
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

# RRF constant — higher k means rank differences matter less.
# k=60 is the standard from Cormack et al. 2009. Not ablation-tested here.
RRF_K = 60

# Default signal weights. Initial tuning, not grid-searched.
# See module docstring for rationale and known limitations.
DEFAULT_WEIGHTS = {
    "vector": 0.60,
    "keyword": 0.25,
    "tag": 0.15,
}


class SearchEngine:
    """Hybrid search over memories."""

    def __init__(
        self, db: Database, embedding: EmbeddingEngine, *,
        llm: LLMInterface | None = None,
        capabilities: LLMCapabilities | None = None,
    ):
        self.db = db
        self.embedding = embedding
        self.llm = llm
        self.capabilities = capabilities

    def search(
        self,
        query: str,
        project: str | None = None,
        memory_type: str | None = None,
        search_mode: str = "semantic",
        limit: int = 10,
        include_full: bool = False,
    ) -> list[dict]:
        """Search memories using hybrid RRF.

        Args:
            query: Natural language search query.
            project: Filter to a specific project.
            memory_type: Filter to a specific memory type.
            search_mode: "semantic" (hybrid), "keyword", or "vector".
            limit: Max results to return.
            include_full: If True, return full content. If False, return summary/truncated.

        Returns:
            List of memory dicts with relevance scores.
        """
        # Query expansion: rewrite query with richer terms before search
        expanded = self._expand_query(query)

        if search_mode == "keyword":
            return self._keyword_search(expanded, project, memory_type, limit, include_full)
        elif search_mode == "vector":
            return self._vector_search(expanded, project, memory_type, limit, include_full)
        else:
            return self._hybrid_search(expanded, project, memory_type, limit, include_full)

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

    def _build_filters(self, project: str | None, memory_type: str | None) -> tuple[str, list]:
        """Build WHERE clause fragments for common filters."""
        clauses = ["m.is_active = true"]
        params = []

        if project:
            clauses.append("p.name = %s")
            params.append(project)

        if memory_type:
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
        self, query: str, project: str | None, memory_type: str | None,
        limit: int, include_full: bool,
    ) -> list[dict]:
        """Hybrid search: vector + keyword + tag, fused via RRF."""
        query_vector = self.embedding.embed(query)
        where, params = self._build_filters(project, memory_type)

        # Fetch a generous candidate set from each signal
        candidate_limit = limit * 5

        # Signal 1: Vector search
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

        # Signal 2: Keyword search
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

        # Signal 3: Tag search (match query words against tags)
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

        # Fuse via RRF
        all_ids = set(vector_ranks) | set(keyword_ranks) | set(tag_ranks)
        if not all_ids:
            return []

        scored = {}
        for memory_id in all_ids:
            score = 0.0
            if memory_id in vector_ranks:
                score += DEFAULT_WEIGHTS["vector"] * (1.0 / (RRF_K + vector_ranks[memory_id]))
            if memory_id in keyword_ranks:
                score += DEFAULT_WEIGHTS["keyword"] * (1.0 / (RRF_K + keyword_ranks[memory_id]))
            if memory_id in tag_ranks:
                score += DEFAULT_WEIGHTS["tag"] * (1.0 / (RRF_K + tag_ranks[memory_id]))
            scored[memory_id] = score

        # Penalize contradicted memories before ranking
        scored = self._apply_contradiction_penalty(scored)

        # Sort by fused score, take top N
        top_ids = sorted(scored, key=scored.get, reverse=True)[:limit]

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

        # Re-order by RRF score and attach scores
        row_map = {r["id"]: r for r in rows}
        results = []
        for memory_id in top_ids:
            if memory_id in row_map:
                r = row_map[memory_id]
                r["score"] = round(scored[memory_id], 6)
                results.append(r)

        return self._format_results(results, include_full, prescored=True)

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
