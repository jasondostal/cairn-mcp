#!/usr/bin/env python3
"""Build graph edges for spreading activation on an eval database.

Creates three types of edges:
1. Temporal edges (same session, sequential by ID) — pure SQL
2. Entity co-occurrence edges (share 2+ entities) — pure SQL
3. LLM relationship extraction (semantic relations) — Bedrock, parallel

Then computes PageRank.

Usage:
    python scripts/build_graph_edges.py --db cairn_eval_locomo_titan_v2
    python scripts/build_graph_edges.py --db cairn_eval_locomo_titan_v2 --workers 16
    python scripts/build_graph_edges.py --db cairn_eval_locomo_titan_v2 --skip-llm
"""

import argparse
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cairn.config import load_config
from cairn.core.utils import extract_json
from cairn.llm import get_llm
from cairn.llm.prompts import build_relationship_extraction_messages

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_temporal_edges(dsn: str) -> int:
    """Create temporal edges between sequential memories in the same session."""
    with psycopg.connect(dsn) as conn:
        result = conn.execute("""
            INSERT INTO memory_relations (source_id, target_id, relation, edge_weight)
            SELECT prev.id, curr.id, 'temporal', 0.8
            FROM memories curr
            JOIN LATERAL (
                SELECT id FROM memories
                WHERE session_name = curr.session_name
                    AND project_id = curr.project_id
                    AND id < curr.id
                    AND is_active = true
                ORDER BY id DESC LIMIT 1
            ) prev ON true
            WHERE curr.is_active = true AND curr.session_name IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        conn.commit()
        count = result.rowcount
        logger.info("Temporal edges created: %d", count)
        return count


def build_entity_cooccurrence_edges(dsn: str) -> int:
    """Create edges between memories sharing 2+ entities."""
    with psycopg.connect(dsn) as conn:
        result = conn.execute("""
            INSERT INTO memory_relations (source_id, target_id, relation, edge_weight)
            SELECT DISTINCT a.id, b.id, 'related', 0.6
            FROM memories a
            JOIN memories b ON a.id < b.id
                AND a.project_id = b.project_id
                AND a.is_active = true AND b.is_active = true
                AND a.entities != '{}' AND b.entities != '{}'
            WHERE (
                SELECT count(*) FROM unnest(a.entities) ae
                WHERE ae = ANY(b.entities)
            ) >= 2
            ON CONFLICT DO NOTHING
        """)
        conn.commit()
        count = result.rowcount
        logger.info("Entity co-occurrence edges created: %d", count)
        return count


def build_llm_relation_edges(dsn: str, workers: int = 16) -> dict:
    """Extract semantic relationships via LLM for all memories."""
    config = load_config()
    llm = get_llm(config.llm)

    stats = {"processed": 0, "edges_created": 0, "errors": 0}
    stats_lock = threading.Lock()

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        # Get all memories with embeddings
        rows = conn.execute("""
            SELECT id, content, embedding::text
            FROM memories
            WHERE is_active = true AND embedding IS NOT NULL
            ORDER BY id
        """).fetchall()

        total = len(rows)
        logger.info("Processing %d memories for LLM relation extraction (%d workers)", total, workers)

        t_start = time.time()
        pending_edges = []
        pending_lock = threading.Lock()

        def _process(row):
            try:
                # Find 15-NN
                with psycopg.connect(dsn, row_factory=dict_row) as thread_conn:
                    neighbors = thread_conn.execute("""
                        SELECT id, content, summary
                        FROM memories
                        WHERE id != %s AND is_active = true AND embedding IS NOT NULL
                        ORDER BY embedding <=> %s::vector
                        LIMIT 15
                    """, (row["id"], row["embedding"])).fetchall()

                if not neighbors:
                    return

                candidates = [
                    {"id": n["id"], "summary": n.get("summary") or n["content"][:300]}
                    for n in neighbors
                ]

                messages = build_relationship_extraction_messages(row["content"], candidates)
                raw = llm.generate(messages, max_tokens=512)
                relations = extract_json(raw, json_type="array")

                if not relations or not isinstance(relations, list):
                    return

                valid_types = {"extends", "contradicts", "implements", "depends_on", "related"}
                candidate_ids = {c["id"] for c in candidates}

                for rel in relations:
                    if not isinstance(rel, dict):
                        continue
                    rel_id = rel.get("id")
                    rel_type = rel.get("relation", "related")
                    if rel_id in candidate_ids and rel_type in valid_types:
                        with pending_lock:
                            pending_edges.append((row["id"], rel_id, rel_type))
                            with stats_lock:
                                stats["edges_created"] += 1

            except Exception as exc:
                with stats_lock:
                    stats["errors"] += 1
            finally:
                with stats_lock:
                    stats["processed"] += 1
                    n = stats["processed"]
                    if n % 100 == 0 or n == total:
                        elapsed = time.time() - t_start
                        rate = n / elapsed if elapsed > 0 else 0
                        eta = (total - n) / rate if rate > 0 else 0
                        logger.info(
                            "  [%d/%d] %.1f/s  ETA %.0fs  (edges=%d errors=%d)",
                            n, total, rate, eta, stats["edges_created"], stats["errors"],
                        )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_process, row) for row in rows]
            for future in as_completed(futures):
                future.result()

        # Batch write
        if pending_edges:
            logger.info("Writing %d LLM relation edges to DB...", len(pending_edges))
            with conn.cursor() as cur:
                for src, tgt, rel_type in pending_edges:
                    cur.execute(
                        """INSERT INTO memory_relations (source_id, target_id, relation)
                           VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                        (src, tgt, rel_type),
                    )
            conn.commit()

    logger.info("LLM relations done: %s", stats)
    return stats


def compute_pagerank(dsn: str) -> int:
    """Compute PageRank for all memories."""
    from cairn.core.activation import ActivationEngine

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        nodes_rows = conn.execute(
            "SELECT id FROM memories WHERE is_active = true"
        ).fetchall()
        nodes = {r["id"] for r in nodes_rows}

        edge_rows = conn.execute("""
            SELECT source_id, target_id, COALESCE(edge_weight, 1.0) as weight
            FROM memory_relations
        """).fetchall()

        edges = {}
        for r in edge_rows:
            edges.setdefault(r["source_id"], []).append(
                (r["target_id"], float(r["weight"]))
            )

        logger.info("Computing PageRank: %d nodes, %d edges", len(nodes), len(edge_rows))
        pr = ActivationEngine.compute_pagerank(nodes, edges)

        # Write PageRank scores
        with conn.cursor() as cur:
            for nid, score in pr.items():
                cur.execute(
                    "UPDATE memories SET pagerank = %s WHERE id = %s",
                    (score, nid),
                )
        conn.commit()

        nonzero = sum(1 for v in pr.values() if v > 1e-6)
        logger.info("PageRank computed: %d nonzero scores", nonzero)
        return nonzero


def main():
    parser = argparse.ArgumentParser(description="Build graph edges for spreading activation")
    parser.add_argument("--db", required=True, help="Database name")
    parser.add_argument("--workers", "-w", type=int, default=16, help="Parallel workers for LLM extraction")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM relation extraction (temporal + entity only)")
    args = parser.parse_args()

    config = load_config()
    base = config.db.dsn.rsplit("/", 1)[0]
    dsn = f"{base}/{args.db}"

    logger.info("Building graph edges for: %s", args.db)

    t0 = time.time()

    # Phase 1: Temporal edges (fast SQL)
    temporal = build_temporal_edges(dsn)

    # Phase 2: Entity co-occurrence (fast SQL)
    entity = build_entity_cooccurrence_edges(dsn)

    # Phase 3: LLM relations (slow, parallel)
    llm_stats = {}
    if not args.skip_llm:
        llm_stats = build_llm_relation_edges(dsn, workers=args.workers)

    # Phase 4: PageRank
    pr_count = compute_pagerank(dsn)

    elapsed = time.time() - t0
    logger.info(
        "Done in %.1fs — temporal=%d, entity=%d, llm=%s, pagerank_nonzero=%d",
        elapsed, temporal, entity, llm_stats.get("edges_created", 0), pr_count,
    )


if __name__ == "__main__":
    main()
