#!/usr/bin/env python3
"""Backfill knowledge graph extraction for memories not yet in Neo4j.

Finds memories that have no Statement nodes (by episode_id) in Neo4j,
runs KnowledgeExtractor.extract() + resolve_and_persist() on each,
then resolves dangling objects.

Usage:
    python scripts/backfill_knowledge_graph.py
    python scripts/backfill_knowledge_graph.py --dry-run
    python scripts/backfill_knowledge_graph.py --batch-size 50
    python scripts/backfill_knowledge_graph.py --project cairn
"""

import argparse
import logging
import os
import sys
import time

import psycopg
from psycopg.rows import dict_row

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cairn.config import load_config
from cairn.core.extraction import KnowledgeExtractor
from cairn.embedding import get_embedding_engine
from cairn.graph import get_graph_provider
from cairn.llm import get_llm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_extracted_episode_ids(graph) -> set[int]:
    """Query Neo4j for all memory IDs that already have Statement nodes."""
    with graph._session() as session:
        result = session.run(
            "MATCH (s:Statement) WHERE s.episode_id IS NOT NULL "
            "RETURN DISTINCT s.episode_id AS episode_id"
        )
        return {r["episode_id"] for r in result}


def get_unextracted_memories(
    dsn: str,
    extracted_ids: set[int],
    project: str | None = None,
    batch_size: int = 500,
) -> list[dict]:
    """Fetch active memories not yet in the knowledge graph."""
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        if project:
            rows = conn.execute(
                """
                SELECT m.id, m.content, m.author, m.created_at, m.project_id,
                       p.name AS project_name
                FROM memories m
                JOIN projects p ON p.id = m.project_id
                WHERE m.is_active = true AND p.name = %s
                ORDER BY m.id
                LIMIT %s
                """,
                (project, batch_size),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT m.id, m.content, m.author, m.created_at, m.project_id,
                       p.name AS project_name
                FROM memories m
                JOIN projects p ON p.id = m.project_id
                WHERE m.is_active = true
                ORDER BY m.id
                LIMIT %s
                """,
                (batch_size,),
            ).fetchall()

    return [r for r in rows if r["id"] not in extracted_ids]


def backfill(
    dsn: str,
    project: str | None = None,
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict:
    """Run knowledge extraction on un-extracted memories."""
    config = load_config()

    # Set up components
    llm = get_llm(config.llm)
    if not llm:
        logger.error("LLM not available — cannot extract knowledge")
        return {"error": "LLM not available"}

    embedding = get_embedding_engine(config.embedding)
    graph = get_graph_provider(config.neo4j)
    if not graph:
        logger.error("Neo4j not available — set CAIRN_GRAPH_BACKEND=neo4j")
        return {"error": "Neo4j not available"}

    graph.connect()
    graph.ensure_schema()

    extractor = KnowledgeExtractor(llm, embedding, graph)

    # Find what's already extracted
    logger.info("Querying Neo4j for already-extracted memories...")
    extracted_ids = get_extracted_episode_ids(graph)
    logger.info("Found %d memories already in graph", len(extracted_ids))

    # Find un-extracted memories
    logger.info("Querying Postgres for un-extracted memories...")
    memories = get_unextracted_memories(dsn, extracted_ids, project, batch_size)
    total = len(memories)
    logger.info("Found %d memories to extract", total)

    if total == 0:
        logger.info("Nothing to do — all memories already extracted")
        return {"processed": 0, "extracted": 0, "errors": 0}

    stats = {
        "processed": 0,
        "extracted": 0,
        "entities_created": 0,
        "entities_merged": 0,
        "statements_created": 0,
        "contradictions_found": 0,
        "errors": 0,
    }

    t_start = time.time()

    for i, mem in enumerate(memories, 1):
        mem_id = mem["id"]
        project_id = mem["project_id"]
        content = mem["content"]
        author = mem.get("author")
        created_at = mem["created_at"].isoformat() if mem.get("created_at") else None

        try:
            # Fetch known entities for canonicalization
            known_entities = None
            try:
                known_entities = graph.get_known_entities(project_id, limit=200)
            except Exception:
                logger.debug("Failed to fetch known entities", exc_info=True)

            # Extract
            result = extractor.extract(
                content, created_at=created_at, author=author,
                known_entities=known_entities,
            )

            if result is None:
                logger.warning("  #%d: extraction returned None, skipping", mem_id)
                stats["errors"] += 1
                stats["processed"] += 1
                continue

            entity_count = len(result.entities)
            stmt_count = len(result.statements)

            if dry_run:
                logger.info(
                    "  [%d/%d] #%d (%s): would extract %d entities, %d statements",
                    i, total, mem_id, mem.get("project_name", "?"),
                    entity_count, stmt_count,
                )
            else:
                # Persist to graph
                graph_stats = extractor.resolve_and_persist(result, mem_id, project_id)
                stats["entities_created"] += graph_stats.get("entities_created", 0)
                stats["entities_merged"] += graph_stats.get("entities_merged", 0)
                stats["statements_created"] += graph_stats.get("statements_created", 0)
                stats["contradictions_found"] += graph_stats.get("contradictions_found", 0)
                logger.info(
                    "  [%d/%d] #%d (%s): +%d entities (%d merged), +%d statements",
                    i, total, mem_id, mem.get("project_name", "?"),
                    graph_stats.get("entities_created", 0),
                    graph_stats.get("entities_merged", 0),
                    graph_stats.get("statements_created", 0),
                )

            stats["extracted"] += 1

        except Exception:
            logger.warning("  #%d: failed", mem_id, exc_info=True)
            stats["errors"] += 1

        stats["processed"] += 1

        # Progress every 25
        if i % 25 == 0:
            elapsed = time.time() - t_start
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            logger.info(
                "  Progress: %d/%d (%.1f/s, ETA %.0fs) — %d extracted, %d errors",
                i, total, rate, eta, stats["extracted"], stats["errors"],
            )

    # Post-extraction: resolve dangling objects across all projects
    if not dry_run and stats["extracted"] > 0:
        project_ids = {m["project_id"] for m in memories}
        total_resolved = 0
        for pid in project_ids:
            try:
                resolved = extractor.resolve_dangling_objects(pid)
                total_resolved += resolved
            except Exception:
                logger.debug("Dangling resolution failed for project %d", pid, exc_info=True)
        if total_resolved > 0:
            logger.info("Resolved %d dangling objects", total_resolved)
            stats["objects_resolved"] = total_resolved

    elapsed = time.time() - t_start
    logger.info("Backfill complete in %.1fs: %s", elapsed, stats)

    graph.close()
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Backfill knowledge graph extraction for un-extracted memories"
    )
    parser.add_argument("--project", default=None, help="Filter to a specific project")
    parser.add_argument("--batch-size", type=int, default=500, help="Max memories to process")
    parser.add_argument("--dry-run", action="store_true", help="Extract but don't persist to Neo4j")
    args = parser.parse_args()

    config = load_config()
    dsn = config.db.dsn

    logger.info("Knowledge graph backfill — DSN: %s", dsn.split("@")[-1])
    if args.dry_run:
        logger.info("DRY RUN — will not persist to Neo4j")

    backfill(dsn, project=args.project, batch_size=args.batch_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
