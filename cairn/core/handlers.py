"""Typed search handlers for search_v2.

Each handler is optimized for a specific query type, using Neo4j graph
queries and/or PostgreSQL as appropriate. All handlers return a list
of candidate dicts with memory IDs and scores.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.router import RouterOutput
    from cairn.embedding.interface import EmbeddingInterface
    from cairn.graph.interface import GraphProvider
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


@dataclass
class SearchContext:
    """Shared context for search handlers."""
    query: str
    route: RouterOutput
    project_id: int | None
    project_name: str | None
    db: Database
    embedding: EmbeddingInterface
    graph: GraphProvider | None
    limit: int = 10
    resolved_entities: list | None = None


def handle_aspect_query(ctx: SearchContext) -> list[dict]:
    """Search by aspect — find statements matching aspects, return their episodes.

    When entity_hints are present, scope to statements about those entities.
    Also blends in vector search results to catch what the graph misses.

    Best for: "What are X's preferences?" "What decisions were made?"
    """
    if not ctx.graph or not ctx.route.aspects:
        return _vector_search(ctx)

    try:
        if ctx.project_id is None:
            return []

        # If we have entity hints, find episodes via entity→statement→aspect path
        graph_episode_ids: list[int] = []
        if ctx.route.entity_hints:
            for hint in ctx.route.entity_hints:
                name_emb = ctx.embedding.embed(hint)
                entities = ctx.graph.search_entities_by_embedding(
                    name_emb, ctx.project_id, limit=5,
                )
                for entity in entities:
                    stmts = ctx.graph.find_entity_statements(
                        entity.uuid, aspects=ctx.route.aspects,
                    )
                    for s in stmts:
                        if s.episode_id:
                            graph_episode_ids.append(s.episode_id)

        # Also get aspect-only results (broader), but cap to avoid flooding
        aspect_episode_ids = ctx.graph.search_statements_by_aspect(
            ctx.route.aspects, ctx.project_id,
        )
        graph_episode_ids.extend(aspect_episode_ids[:ctx.limit])

        # Vector search is primary — graph supplements with entity-matched results
        vector_results = _vector_search(ctx, limit=ctx.limit * 3)
        graph_results = _fetch_memories_by_ids(ctx.db, graph_episode_ids, ctx.limit)

        return _blend_results(vector_results, graph_results, ctx.limit * 3)
    except Exception:
        logger.warning("Aspect query handler failed", exc_info=True)
        return _vector_search(ctx)


def handle_entity_lookup(ctx: SearchContext) -> list[dict]:
    """Entity-centric graph-primary search with multi-hop BFS.

    Uses pre-resolved entities from SearchV2's query entity extraction
    when available, avoiding redundant embedding + resolution calls.

    Multi-hop BFS inspired by Core:
    - Hop 1: Direct statements connected to query entities (score 2.0x)
    - Hop 2: Statements connected to hop-1 entities (score 1.3x)

    Falls back to string-based resolution from entity_hints if no
    pre-resolved entities are provided.
    """
    if not ctx.graph:
        return _vector_search(ctx)

    try:
        if ctx.project_id is None:
            return []

        # Use pre-resolved entities if available, else resolve from hints
        entities = ctx.resolved_entities or []
        if not entities and ctx.route.entity_hints:
            seen_uuids = set()
            for hint in ctx.route.entity_hints:
                name_embedding = ctx.embedding.embed(hint)
                for e in ctx.graph.search_entities_by_embedding(
                    name_embedding, ctx.project_id, limit=5,
                ):
                    if e.uuid not in seen_uuids:
                        seen_uuids.add(e.uuid)
                        entities.append(e)

        if not entities:
            return _vector_search(ctx)

        # --- Multi-hop BFS ---
        # Hop 1: Direct entity → statement → episode_id (score boost 2.0)
        hop1_episodes: dict[int, float] = {}
        hop1_entity_uuids: set[str] = set()

        for entity in entities:
            hop1_entity_uuids.add(entity.uuid)
            episode_ids = ctx.graph.find_entity_episodes(entity.uuid)
            for eid in episode_ids:
                hop1_episodes[eid] = max(hop1_episodes.get(eid, 0), 2.0)

        # Hop 2: BFS depth=2 from each entity, collect statements not in hop1
        hop2_episodes: dict[int, float] = {}
        for entity in entities:
            try:
                stmts = ctx.graph.bfs_traverse(entity.uuid, max_depth=2)
                for stmt in stmts:
                    if stmt.episode_id and stmt.episode_id not in hop1_episodes:
                        hop2_episodes[stmt.episode_id] = max(
                            hop2_episodes.get(stmt.episode_id, 0), 1.3,
                        )
            except Exception:
                logger.debug(
                    "BFS hop-2 failed for entity %s", entity.uuid, exc_info=True,
                )

        # Merge hop1 and hop2 episode IDs with their scores
        scored_episodes = {**hop2_episodes, **hop1_episodes}  # hop1 overwrites hop2

        if not scored_episodes:
            return []

        # Fetch memories and apply hop scores
        all_ids = list(scored_episodes.keys())
        graph_results = _fetch_memories_by_ids(ctx.db, all_ids, ctx.limit * 3)
        for r in graph_results:
            r["score"] = scored_episodes.get(r["id"], 1.0) * r.get("score", 1.0)

        # Sort by score descending
        graph_results.sort(key=lambda r: r["score"], reverse=True)

        logger.debug(
            "Entity lookup: %d entities → %d hop1 + %d hop2 episodes → %d memories",
            len(entities), len(hop1_episodes), len(hop2_episodes), len(graph_results),
        )

        return graph_results

    except Exception:
        logger.warning("Entity lookup handler failed", exc_info=True)
        return _vector_search(ctx)


def handle_temporal(ctx: SearchContext) -> list[dict]:
    """Time-range search — PostgreSQL time filters, optionally with aspect filter.

    Best for: "What happened last week?" "Recent deployments"
    """
    try:
        where_clauses = ["m.is_active = true"]
        params: list = []

        if ctx.project_name:
            where_clauses.append("p.name = %s")
            params.append(ctx.project_name)

        # Temporal filters
        if ctx.route.temporal.after:
            where_clauses.append("m.created_at >= %s::timestamptz")
            params.append(ctx.route.temporal.after)

        if ctx.route.temporal.before:
            where_clauses.append("m.created_at <= %s::timestamptz")
            params.append(ctx.route.temporal.before)

        # If no temporal filter was extracted, default to recent (last 7 days)
        if not ctx.route.temporal.after and not ctx.route.temporal.before:
            where_clauses.append("m.created_at >= NOW() - INTERVAL '7 days'")

        where = " AND ".join(where_clauses)

        rows = ctx.db.execute(
            f"""
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.created_at,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where}
            ORDER BY m.created_at DESC
            LIMIT %s
            """,
            tuple(params) + (ctx.limit * 2,),
        )

        return [
            {
                "id": r["id"],
                "content": r["content"],
                "row": r,
                "score": 1.0 / (i + 1),  # Recency ordering
            }
            for i, r in enumerate(rows)
        ]
    except Exception:
        logger.warning("Temporal handler failed, falling back to vector search", exc_info=True)
        return _vector_search(ctx)


def handle_exploratory(ctx: SearchContext) -> list[dict]:
    """Broad search — vector similarity + graph entity episodes when available.

    Best for: vague queries, general exploration, fallback from other handlers.
    """
    try:
        vector_results = _vector_search(ctx, limit=ctx.limit * 3)

        # If we have entity hints and a graph, blend in entity episodes
        if ctx.graph and ctx.route.entity_hints and ctx.project_id:
            graph_episode_ids = set()
            for hint in ctx.route.entity_hints:
                try:
                    name_emb = ctx.embedding.embed(hint)
                    entities = ctx.graph.search_entities_by_embedding(
                        name_emb, ctx.project_id, limit=5,
                    )
                    for entity in entities:
                        eps = ctx.graph.find_entity_episodes(entity.uuid)
                        graph_episode_ids.update(eps)
                except Exception:
                    pass

            if graph_episode_ids:
                graph_results = _fetch_memories_by_ids(ctx.db, list(graph_episode_ids), ctx.limit)
                return _blend_results(vector_results, graph_results, ctx.limit * 3)

        return vector_results
    except Exception:
        logger.warning("Exploratory handler failed", exc_info=True)
        return []


def handle_relationship(ctx: SearchContext) -> list[dict]:
    """Relationship search — BFS between entity pairs via Neo4j.

    Best for: "How are X and Y related?" "Connection between A and B"
    """
    if not ctx.graph or len(ctx.route.entity_hints) < 2:
        return []

    try:
        if ctx.project_id is None:
            return []

        # Resolve the first two entity hints
        entity_uuids = []
        for hint in ctx.route.entity_hints[:2]:
            name_embedding = ctx.embedding.embed(hint)
            entities = ctx.graph.search_entities_by_embedding(
                name_embedding, ctx.project_id, limit=1,
            )
            if entities:
                entity_uuids.append(entities[0].uuid)

        if len(entity_uuids) < 2:
            return []

        # BFS for connecting statements
        statements = ctx.graph.find_connecting_statements(
            entity_uuids[0], entity_uuids[1],
        )

        if not statements:
            return []

        episode_ids = list({s.episode_id for s in statements if s.episode_id})
        if not episode_ids:
            return []

        return _fetch_memories_by_ids(ctx.db, episode_ids, ctx.limit * 2)
    except Exception:
        logger.warning("Relationship handler failed", exc_info=True)
        return []


# Handler dispatch map
HANDLERS = {
    "aspect_query": handle_aspect_query,
    "entity_lookup": handle_entity_lookup,
    "temporal": handle_temporal,
    "exploratory": handle_exploratory,
    "relationship": handle_relationship,
}


def _vector_search(ctx: SearchContext, limit: int | None = None) -> list[dict]:
    """Standard pgvector cosine similarity search."""
    search_limit = limit or ctx.limit * 3
    try:
        query_vector = ctx.embedding.embed(ctx.query)
        where_clauses = ["m.is_active = true", "m.embedding IS NOT NULL"]
        params: list = []

        if ctx.project_name:
            where_clauses.append("p.name = %s")
            params.append(ctx.project_name)

        where = " AND ".join(where_clauses)

        rows = ctx.db.execute(
            f"""
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.created_at,
                   p.name as project,
                   1 - (m.embedding <=> %s::vector) as score
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE {where}
            ORDER BY m.embedding <=> %s::vector
            LIMIT %s
            """,
            [str(query_vector)] + params + [str(query_vector), search_limit],
        )

        return [
            {
                "id": r["id"],
                "content": r["content"],
                "row": r,
                "score": float(r["score"]),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("Vector search failed", exc_info=True)
        return []


def _blend_results(
    primary: list[dict],
    supplement: list[dict],
    limit: int,
) -> list[dict]:
    """Merge primary and supplementary results, dedup by ID, primary order preserved."""
    seen_ids = set()
    blended = []

    for r in primary:
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            blended.append(r)

    for r in supplement:
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            blended.append(r)

    return blended[:limit]


def _fetch_memories_by_ids(db: Database, memory_ids: list[int], limit: int) -> list[dict]:
    """Fetch full memory rows for a set of IDs."""
    if not memory_ids:
        return []

    # Deduplicate and cap
    unique_ids = list(dict.fromkeys(memory_ids))[:limit]
    placeholders = ",".join(["%s"] * len(unique_ids))

    rows = db.execute(
        f"""
        SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
               m.tags, m.auto_tags, m.created_at,
               p.name as project
        FROM memories m
        LEFT JOIN projects p ON m.project_id = p.id
        WHERE m.id IN ({placeholders}) AND m.is_active = true
        """,
        tuple(unique_ids),
    )

    row_map = {r["id"]: r for r in rows}
    return [
        {
            "id": mid,
            "content": row_map[mid]["content"],
            "row": row_map[mid],
            "score": 1.0 / (i + 1),
        }
        for i, mid in enumerate(unique_ids)
        if mid in row_map
    ]
