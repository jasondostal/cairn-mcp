"""Database connection and migration management."""

import logging
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from cairn.config import DatabaseConfig

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Database:
    """PostgreSQL connection manager with migration support."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._conn = None

    def connect(self) -> None:
        """Establish connection pool."""
        self._conn = psycopg.Connection.connect(
            self.config.dsn,
            row_factory=dict_row,
            autocommit=False,
        )
        logger.info("Connected to PostgreSQL at %s:%s/%s", self.config.host, self.config.port, self.config.name)

    def close(self) -> None:
        """Close connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> psycopg.Connection:
        """Get the active connection."""
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    def execute(self, query: str, params: tuple | list | None = None) -> list[dict]:
        """Execute a query and return results."""
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return []

    def execute_one(self, query: str, params: tuple | list | None = None) -> dict | None:
        """Execute a query and return a single result."""
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchone()
            return None

    def commit(self) -> None:
        """Commit the current transaction."""
        self.conn.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.conn.rollback()

    def run_migrations(self) -> None:
        """Apply all pending migrations in order."""
        # Create migrations tracking table
        self.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) UNIQUE NOT NULL,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        self.commit()

        # Get already-applied migrations
        applied = {
            row["filename"]
            for row in self.execute("SELECT filename FROM _migrations")
        }

        # Find and apply pending migrations
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for migration_file in migration_files:
            if migration_file.name in applied:
                continue

            logger.info("Applying migration: %s", migration_file.name)
            sql = migration_file.read_text()

            try:
                self.execute(sql)
                self.execute(
                    "INSERT INTO _migrations (filename) VALUES (%s)",
                    (migration_file.name,),
                )
                self.commit()
                logger.info("Migration applied: %s", migration_file.name)
            except Exception:
                self.rollback()
                logger.exception("Migration failed: %s", migration_file.name)
                raise

        logger.info("All migrations applied. %d total.", len(migration_files))
