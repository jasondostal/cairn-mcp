#!/usr/bin/env python3
"""Cairn v2 migration: re-embed all memories and run knowledge extraction.

This script:
1. Re-embeds all memories with the current embedding backend (e.g., Titan V2 1024D)
2. Runs knowledge extraction on all memories → populates Neo4j graph
3. Entity resolution dedup pass

Resumable: tracks last processed ID. Progress logged to stdout.

Usage:
    # Full migration (re-embed + extract)
    python scripts/migrate_v2.py

    # Re-embed only (skip extraction)
    python scripts/migrate_v2.py --embed-only

    # Extract only (skip re-embedding, use existing embeddings)
    python scripts/migrate_v2.py --extract-only

    # Resume from a specific memory ID
    python scripts/migrate_v2.py --resume-from 150

    # Control parallelism (default 8 workers)
    python scripts/migrate_v2.py --workers 12

    # Dry run (show what would be done)
    python scripts/migrate_v2.py --dry-run

Environment:
    Requires standard Cairn env vars (CAIRN_DB_*, CAIRN_EMBEDDING_*, etc.)
    For extraction: CAIRN_GRAPH_BACKEND=neo4j, CAIRN_KNOWLEDGE_EXTRACTION=true
"""

import argparse
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
# Suppress noisy neo4j notification warnings
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
logger = logging.getLogger("migrate_v2")

# Thread-safe counters
_lock = threading.Lock()
_processed = 0
_errors = 0
_entities_total = 0
_statements_total = 0


def process_one(row, svc, extract_only, embed_only):
    """Process a single memory. Called from thread pool."""
    global _processed, _errors, _entities_total, _statements_total

    memory_id = row["id"]
    content = row["content"]
    project_id = row["project_id"]

    try:
        # Step 1: Re-embed
        if not extract_only:
            vector = svc.embedding.embed(content)
            svc.db.execute(
                "UPDATE memories SET embedding = %s::vector WHERE id = %s",
                (str(vector), memory_id),
            )
            svc.db.commit()

        # Step 2: Knowledge extraction
        if not embed_only and svc.knowledge_extractor:
            created_at = row.get("created_at")
            created_at_str = created_at.isoformat() if created_at else None
            author = row.get("author")
            result = svc.knowledge_extractor.extract(
                content, created_at=created_at_str, author=author,
            )
            if result and (result.entities or result.statements):
                stats = svc.knowledge_extractor.resolve_and_persist(
                    result, memory_id, project_id,
                )
                with _lock:
                    _entities_total += stats.get("entities_created", 0)
                    _statements_total += stats.get("statements_created", 0)

        with _lock:
            _processed += 1
        return True

    except Exception:
        logger.warning("Failed to process memory #%d", memory_id, exc_info=True)
        with _lock:
            _errors += 1
        try:
            svc.db.rollback()
        except Exception:
            pass
        return False


def main():
    global _processed, _errors

    parser = argparse.ArgumentParser(description="Cairn v2 migration")
    parser.add_argument("--embed-only", action="store_true", help="Only re-embed, skip extraction")
    parser.add_argument("--extract-only", action="store_true", help="Only extract, skip re-embedding")
    parser.add_argument("--resume-from", type=int, default=0, help="Resume from memory ID")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for fetching")
    parser.add_argument("--workers", type=int, default=16, help="Number of parallel workers")
    parser.add_argument("--db-name", type=str, default=None, help="Override database name (e.g., cairn_eval_locomo_titan_v2)")
    args = parser.parse_args()

    from cairn.config import load_config
    from cairn.core.services import create_services

    logger.info("Loading configuration...")
    config = load_config()

    # Override database name if specified
    if args.db_name:
        import os
        os.environ["CAIRN_DB_NAME"] = args.db_name
        config = load_config()  # Reload with overridden DB name
        logger.info("Database override: %s", args.db_name)

    svc = create_services(config)

    # Connect database
    svc.db.connect()
    svc.db.run_migrations()
    svc.db.reconcile_vector_dimensions(config.embedding.dimensions)

    # Connect graph if extraction is enabled
    if not args.embed_only and svc.graph_provider:
        try:
            svc.graph_provider.connect()
            svc.graph_provider.ensure_schema()
            logger.info("Neo4j connected")
        except Exception:
            logger.error("Failed to connect Neo4j — extraction will be skipped", exc_info=True)

    try:
        # Fetch ALL memory IDs + content upfront (cheaper than batched queries with threads)
        rows = svc.db.execute(
            """
            SELECT id, content, project_id, created_at, author FROM memories
            WHERE is_active = true AND id > %s
            ORDER BY id ASC
            """,
            (args.resume_from,),
        )
        total = len(rows)
        logger.info("Total memories to process: %d (resuming from ID %d)", total, args.resume_from)
        logger.info("Workers: %d", args.workers)

        if args.dry_run:
            logger.info("[DRY RUN] Would process %d memories with %d workers", total, args.workers)
            logger.info("  Embedding backend: %s (%dD)", config.embedding.backend, config.embedding.dimensions)
            logger.info("  Knowledge extraction: %s", "yes" if svc.knowledge_extractor else "no")
            return

        start_time = time.time()

        # Progress reporter thread
        def report_progress():
            while not _done.is_set():
                _done.wait(10)
                elapsed = time.time() - start_time
                rate = _processed / elapsed if elapsed > 0 else 0
                remaining = total - _processed - _errors
                eta = remaining / rate if rate > 0 else 0
                logger.info(
                    "Progress: %d/%d (%.1f%%) | %.1f mem/s | ETA: %.0fs | Errors: %d | Entities: %d | Statements: %d",
                    _processed, total, 100 * _processed / max(total, 1),
                    rate, eta, _errors, _entities_total, _statements_total,
                )

        _done = threading.Event()
        reporter = threading.Thread(target=report_progress, daemon=True)
        reporter.start()

        # Process in parallel
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(process_one, row, svc, args.extract_only, args.embed_only): row["id"]
                for row in rows
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    mid = futures[future]
                    logger.warning("Unhandled error for memory #%d", mid, exc_info=True)

        _done.set()
        reporter.join(timeout=2)

        elapsed = time.time() - start_time
        logger.info(
            "Migration complete: %d processed, %d errors, %.1fs elapsed (%.1f mem/s)",
            _processed, _errors, elapsed, _processed / elapsed if elapsed > 0 else 0,
        )
        logger.info("Graph totals: %d entities created, %d statements created", _entities_total, _statements_total)

    finally:
        if svc.graph_provider:
            try:
                svc.graph_provider.close()
            except Exception:
                pass
        svc.db.close()


if __name__ == "__main__":
    main()
