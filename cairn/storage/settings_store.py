"""DB-persisted settings store for configuration overrides.

Keys use dot notation matching config structure: e.g. 'llm.backend',
'capabilities.query_expansion', 'analytics.retention_days'.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


def load_all(db: Database) -> dict[str, str]:
    """Load all setting overrides from the database."""
    rows = db.execute("SELECT key, value FROM app_settings")
    return {r["key"]: r["value"] for r in rows}


def save_bulk(db: Database, updates: dict[str, str]) -> None:
    """Upsert multiple settings."""
    if not updates:
        return
    for key, value in updates.items():
        db.execute_one(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            (key, value),
        )
    db.commit()
    logger.info("Saved %d setting overrides", len(updates))


def delete(db: Database, key: str) -> bool:
    """Remove a single override (revert to env/default). Returns True if deleted."""
    row = db.execute_one(
        "DELETE FROM app_settings WHERE key = %s RETURNING key",
        (key,),
    )
    db.commit()
    if row:
        logger.info("Deleted setting override: %s", key)
        return True
    return False
