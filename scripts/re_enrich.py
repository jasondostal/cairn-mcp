#!/usr/bin/env python3
"""Re-enrich all active memories through the knowledge extraction pipeline.

Nukes existing Neo4j entities/statements, then re-extracts from scratch
using the current LLM backend. Embeddings in PG are untouched.

Usage (inside cairn container):
    python /app/scripts/re_enrich.py [--dry-run] [--project PROJECT] [--limit N]
"""

import argparse
import logging
import os
import sys
import time

# Ensure cairn package is importable
sys.path.insert(0, "/app")

from cairn.config import load_config
from cairn.core.extraction import KnowledgeExtractor
from cairn.embedding import get_embedding_engine
from cairn.graph import get_graph_provider
from cairn.llm import get_llm
from cairn.storage.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("re_enrich")

# Quiet down noisy loggers
logging.getLogger("neo4j").setLevel(logging.WARNING)
logging.getLogger("cairn.llm").setLevel(logging.WARNING)
logging.getLogger("cairn.embedding").setLevel(logging.WARNING)
logging.getLogger("cairn.graph").setLevel(logging.WARNING)


def nuke_graph(graph):
    """Delete ALL Entity and Statement nodes (and their relationships)."""
    with graph._session() as session:
        # Count before
        result = session.run("MATCH (n) WHERE n:Entity OR n:Statement RETURN count(n) AS c")
        count = result.single()["c"]
        logger.info("Graph has %d Entity+Statement nodes — deleting...", count)

        # Delete in batches to avoid memory issues
        deleted = 0
        while True:
            result = session.run("""
                MATCH (n) WHERE n:Entity OR n:Statement
                WITH n LIMIT 500
                DETACH DELETE n
                RETURN count(*) AS deleted
            """)
            batch = result.single()["deleted"]
            if batch == 0:
                break
            deleted += batch
            logger.info("  deleted %d nodes so far...", deleted)

        logger.info("Graph wiped: %d nodes removed", deleted)
        return deleted


def fetch_memories(db, project=None, limit=None):
    """Fetch all active memories for re-enrichment."""
    query = """
        SELECT m.id, m.content, m.memory_type, m.created_at, m.author,
               p.name AS project_name, p.id AS project_id
        FROM memories m
        JOIN projects p ON m.project_id = p.id
        WHERE m.is_active = true
    """
    params = []
    if project:
        query += " AND p.name = %s"
        params.append(project)
    query += " ORDER BY m.id"
    if limit:
        query += " LIMIT %s"
        params.append(limit)

    return db.execute(query, params)


def main():
    parser = argparse.ArgumentParser(description="Re-enrich all memories")
    parser.add_argument("--dry-run", action="store_true", help="Count only, don't extract")
    parser.add_argument("--project", type=str, help="Filter to specific project")
    parser.add_argument("--limit", type=int, help="Process only N memories")
    parser.add_argument("--skip-nuke", action="store_true", help="Don't clear graph first")
    args = parser.parse_args()

    config = load_config()
    db = Database(config.db)
    db.connect()

    embedding = get_embedding_engine(config.embedding)
    llm = get_llm(config.llm)
    graph = get_graph_provider()  # reads from env vars
    if graph is None:
        logger.error("Neo4j not configured (CAIRN_GRAPH_BACKEND != 'neo4j')")
        sys.exit(1)
    graph.connect()

    logger.info("LLM backend: %s / %s", config.llm.backend, llm.get_model_name())
    logger.info("Embedding: %s", config.embedding.backend)

    extractor = KnowledgeExtractor(llm=llm, embedding=embedding, graph=graph)

    # Fetch memories
    memories = fetch_memories(db, project=args.project, limit=args.limit)
    logger.info("Found %d active memories to re-enrich", len(memories))

    if args.dry_run:
        for m in memories:
            logger.info("  [DRY RUN] #%d (%s) %s — %.60s...",
                        m["id"], m["project_name"], m["memory_type"],
                        m["content"][:60].replace("\n", " "))
        logger.info("Dry run complete. %d memories would be processed.", len(memories))
        return

    # Nuke existing graph
    if not args.skip_nuke:
        nuke_graph(graph)

    # Re-extract
    stats = {
        "processed": 0, "skipped": 0, "failed": 0,
        "entities_created": 0, "entities_merged": 0,
        "statements_created": 0, "contradictions_found": 0,
    }
    t0 = time.monotonic()

    for i, m in enumerate(memories):
        mem_id = m["id"]
        project_id = m["project_id"]
        content = m["content"]
        created_at = m["created_at"].isoformat() if m["created_at"] else None

        try:
            # Get known entities for better canonicalization
            known = graph.get_known_entities(project_id) if stats["entities_created"] > 0 else []

            result = extractor.extract(
                content=content,
                created_at=created_at,
                author=m.get("author"),
                known_entities=known,
            )

            if result is None:
                stats["skipped"] += 1
                logger.info("[%d/%d] #%d SKIP (no facts)", i + 1, len(memories), mem_id)
                continue

            graph_stats = extractor.resolve_and_persist(result, episode_id=mem_id, project_id=project_id)

            stats["processed"] += 1
            stats["entities_created"] += graph_stats["entities_created"]
            stats["entities_merged"] += graph_stats["entities_merged"]
            stats["statements_created"] += graph_stats["statements_created"]
            stats["contradictions_found"] += graph_stats["contradictions_found"]

            elapsed = time.monotonic() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(memories) - i - 1) / rate if rate > 0 else 0

            logger.info(
                "[%d/%d] #%d OK — %d entities (+%d merged), %d stmts | %.1f/min | ETA %.0fs",
                i + 1, len(memories), mem_id,
                graph_stats["entities_created"], graph_stats["entities_merged"],
                graph_stats["statements_created"],
                rate * 60, eta,
            )

        except Exception as e:
            stats["failed"] += 1
            logger.error("[%d/%d] #%d FAILED: %s", i + 1, len(memories), mem_id, e)

    # Final pass: resolve dangling objects
    logger.info("Resolving dangling objects...")
    projects = db.execute("SELECT id FROM projects")
    total_resolved = 0
    for p in projects:
        resolved = extractor.resolve_dangling_objects(p["id"])
        total_resolved += resolved

    elapsed = time.monotonic() - t0
    logger.info("=" * 60)
    logger.info("RE-ENRICHMENT COMPLETE in %.1f minutes", elapsed / 60)
    logger.info("  Processed: %d", stats["processed"])
    logger.info("  Skipped (no facts): %d", stats["skipped"])
    logger.info("  Failed: %d", stats["failed"])
    logger.info("  Entities created: %d", stats["entities_created"])
    logger.info("  Entities merged: %d", stats["entities_merged"])
    logger.info("  Statements created: %d", stats["statements_created"])
    logger.info("  Contradictions: %d", stats["contradictions_found"])
    logger.info("  Dangling objects resolved: %d", total_resolved)


if __name__ == "__main__":
    main()
