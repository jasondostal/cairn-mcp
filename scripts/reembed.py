#!/usr/bin/env python3
"""Re-embed all memories with NULL embeddings using the configured backend.

Run after switching embedding backends (e.g. local → Bedrock) to backfill
existing memories with new vectors.

Usage (inside container):
    python scripts/reembed.py

The script reads CAIRN_* env vars to connect to the database and instantiate
the configured embedding engine. Progress is logged every 50 memories.
"""

import logging
import time

from cairn.config import load_config
from cairn.embedding import get_embedding_engine
from cairn.storage.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("reembed")


def main():
    config = load_config()
    db = Database(config.db)
    db.connect()

    embedding = get_embedding_engine(config.embedding)
    logger.info(
        "Embedding backend: %s (%d-dim)",
        config.embedding.backend,
        config.embedding.dimensions,
    )

    # Fetch all memories needing re-embedding
    rows = db.execute(
        "SELECT id, content FROM memories WHERE embedding IS NULL AND is_active = true ORDER BY id"
    )
    db.commit()

    total = len(rows)
    if total == 0:
        logger.info("No memories need re-embedding.")
        db.close()
        return

    logger.info("Re-embedding %d memories...", total)
    start = time.time()
    done = 0

    for row in rows:
        try:
            vector = embedding.embed(row["content"])
            db.execute(
                "UPDATE memories SET embedding = %s WHERE id = %s",
                (vector, row["id"]),
            )
            db.commit()
            done += 1

            if done % 50 == 0:
                elapsed = time.time() - start
                logger.info(
                    "Progress: %d/%d (%.1f%%) — %.1fs elapsed",
                    done, total, done / total * 100, elapsed,
                )
        except Exception:
            db.rollback()
            logger.exception("Failed to re-embed memory %d", row["id"])

    elapsed = time.time() - start
    logger.info(
        "Done. Re-embedded %d/%d memories in %.1fs.",
        done, total, elapsed,
    )

    # Rough cost estimate for Bedrock Titan V2 (~$0.02/1M tokens, ~100 tokens avg per memory)
    if config.embedding.backend == "bedrock":
        est_tokens = done * 100
        est_cost = est_tokens / 1_000_000 * 0.02
        logger.info("Estimated Bedrock cost: ~$%.4f (%d est. tokens)", est_cost, est_tokens)

    db.close()


if __name__ == "__main__":
    main()
