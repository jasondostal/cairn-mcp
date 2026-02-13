#!/usr/bin/env python3
"""Backfill entities on existing memories via LLM enrichment.

Usage:
    python scripts/backfill_entities.py
    python scripts/backfill_entities.py --db cairn_eval_locomo_titan_v2
    python scripts/backfill_entities.py --batch-size 50 --dry-run
    python scripts/backfill_entities.py --workers 16
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

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cairn.config import load_config
from cairn.core.utils import extract_json
from cairn.llm import get_llm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ENTITY_PROMPT = """\
Extract named entities from the following text. Return a JSON object with a single field:

{"entities": ["Entity Name 1", "Entity Name 2", ...]}

Extract people, places, organizations, projects, products, and technologies.
Preserve original casing. Only extract entities explicitly mentioned.
Return 0-15 entities. Return ONLY the JSON object."""


def _extract_entities(llm, row: dict) -> tuple[int, list[str] | None, str | None]:
    """Extract entities for a single memory. Returns (id, entities, error)."""
    try:
        messages = [
            {"role": "system", "content": ENTITY_PROMPT},
            {"role": "user", "content": row["content"][:4000]},
        ]
        raw = llm.generate(messages, max_tokens=512)
        data = extract_json(raw, json_type="object")

        if not data or "entities" not in data:
            return (row["id"], None, None)

        entities = [
            str(e).strip() for e in data["entities"]
            if e and str(e).strip()
        ][:15]

        return (row["id"], entities, None)
    except Exception as exc:
        return (row["id"], None, str(exc))


def backfill(dsn: str, batch_size: int = 3000, workers: int = 16, dry_run: bool = False) -> dict:
    """Backfill entities for memories that have empty entities arrays."""
    config = load_config()
    llm = get_llm(config.llm)

    stats = {"processed": 0, "updated": 0, "errors": 0, "skipped": 0}
    stats_lock = threading.Lock()

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT id, content FROM memories
            WHERE is_active = true AND (entities IS NULL OR entities = '{}')
            ORDER BY id
            LIMIT %s
            """,
            (batch_size,),
        ).fetchall()

        total = len(rows)
        logger.info("Found %d memories to backfill (%d workers)", total, workers)

        if total == 0:
            return stats

        t_start = time.time()
        pending_updates: list[tuple[int, list[str]]] = []
        pending_lock = threading.Lock()

        def _process(row):
            mem_id, entities, error = _extract_entities(llm, row)
            with stats_lock:
                stats["processed"] += 1
                n = stats["processed"]
                if error:
                    stats["errors"] += 1
                elif entities is None:
                    stats["skipped"] += 1
                else:
                    stats["updated"] += 1
                    if not dry_run:
                        with pending_lock:
                            pending_updates.append((mem_id, entities))

                if n % 50 == 0 or n == total:
                    elapsed = time.time() - t_start
                    rate = n / elapsed if elapsed > 0 else 0
                    eta = (total - n) / rate if rate > 0 else 0
                    logger.info(
                        "  [%d/%d] %.1f/s  ETA %.0fs  (updated=%d errors=%d)",
                        n, total, rate, eta, stats["updated"], stats["errors"],
                    )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_process, row) for row in rows]
            for future in as_completed(futures):
                future.result()  # Raise any unexpected exceptions

        # Batch-write all updates
        if not dry_run and pending_updates:
            logger.info("Writing %d entity updates to DB...", len(pending_updates))
            with conn.cursor() as cur:
                for mem_id, entities in pending_updates:
                    cur.execute(
                        "UPDATE memories SET entities = %s WHERE id = %s",
                        (entities, mem_id),
                    )
            conn.commit()
            logger.info("Committed.")

    elapsed = time.time() - t_start
    logger.info("Backfill complete in %.1fs: %s", elapsed, stats)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill entities on existing memories")
    parser.add_argument("--db", default=None, help="Database name (overrides CAIRN_DB_NAME)")
    parser.add_argument("--batch-size", type=int, default=3000, help="Batch size")
    parser.add_argument("--workers", "-w", type=int, default=16, help="Parallel workers (default: 16)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes")
    args = parser.parse_args()

    config = load_config()
    dsn = config.db.dsn
    if args.db:
        base = dsn.rsplit("/", 1)[0]
        dsn = f"{base}/{args.db}"

    logger.info("Backfilling entities in: %s", dsn.split("@")[-1])
    backfill(dsn, batch_size=args.batch_size, workers=args.workers, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
