#!/usr/bin/env python3
"""Backfill entities on existing memories via LLM enrichment.

Usage:
    python scripts/backfill_entities.py
    python scripts/backfill_entities.py --db cairn_eval_locomo_titan_v2
    python scripts/backfill_entities.py --batch-size 50 --dry-run
"""

import argparse
import json
import logging
import os
import sys

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


def backfill(dsn: str, batch_size: int = 100, dry_run: bool = False) -> dict:
    """Backfill entities for memories that have empty entities arrays."""
    config = load_config()
    llm = get_llm(config.llm)

    stats = {"processed": 0, "updated": 0, "errors": 0, "skipped": 0}

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        # Find memories with empty entities
        rows = conn.execute(
            """
            SELECT id, content FROM memories
            WHERE is_active = true AND (entities IS NULL OR entities = '{}')
            ORDER BY id
            LIMIT %s
            """,
            (batch_size,),
        ).fetchall()

        logger.info("Found %d memories to backfill", len(rows))

        for row in rows:
            stats["processed"] += 1
            try:
                messages = [
                    {"role": "system", "content": ENTITY_PROMPT},
                    {"role": "user", "content": row["content"][:4000]},
                ]
                raw = llm.generate(messages, max_tokens=512)
                data = extract_json(raw, json_type="object")

                if not data or "entities" not in data:
                    stats["skipped"] += 1
                    continue

                entities = [
                    str(e).strip() for e in data["entities"]
                    if e and str(e).strip()
                ][:15]

                if dry_run:
                    logger.info("  [DRY RUN] #%d: %s", row["id"], entities)
                else:
                    conn.execute(
                        "UPDATE memories SET entities = %s WHERE id = %s",
                        (entities, row["id"]),
                    )
                stats["updated"] += 1

            except Exception:
                logger.warning("Failed for memory #%d", row["id"], exc_info=True)
                stats["errors"] += 1

            if stats["processed"] % 25 == 0:
                logger.info("  Progress: %d/%d", stats["processed"], len(rows))

        if not dry_run:
            conn.commit()

    logger.info("Backfill complete: %s", stats)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill entities on existing memories")
    parser.add_argument("--db", default=None, help="Database name (overrides CAIRN_DB_NAME)")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes")
    args = parser.parse_args()

    config = load_config()
    dsn = config.db.dsn
    if args.db:
        # Replace database name in DSN
        base = dsn.rsplit("/", 1)[0]
        dsn = f"{base}/{args.db}"

    logger.info("Backfilling entities in: %s", dsn.split("@")[-1])
    backfill(dsn, batch_size=args.batch_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
