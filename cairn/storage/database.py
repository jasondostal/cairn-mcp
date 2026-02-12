"""Database connection pool and migration management.

Uses psycopg_pool.ConnectionPool for thread-safe concurrent access.
Each thread gets its own connection via thread-local storage:
  - First execute() on a thread checks out a connection from the pool
  - commit() / rollback() return the connection to the pool
  - Stale transactions (from uncaught exceptions) are auto-rolled back
    on the next access from the same thread

This is critical for the REST API (FastAPI + uvicorn threadpool) where
concurrent requests would otherwise race on a single shared connection.
MCP stdio (serial) works fine too — it just uses one connection at a time.
"""

import logging
import threading
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from cairn.config import DatabaseConfig

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Pool sizing: min_size covers typical concurrent load (MCP + API + dashboard),
# max_size caps runaway connections. Adjust via subclass if needed.
POOL_MIN_SIZE = 2
POOL_MAX_SIZE = 10


class Database:
    """PostgreSQL connection pool with thread-local connection tracking."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool: ConnectionPool | None = None
        self._local = threading.local()

    def connect(self) -> None:
        """Initialize the connection pool."""
        self._pool = ConnectionPool(
            self.config.dsn,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            kwargs={"row_factory": dict_row, "autocommit": False},
        )
        # Block until min_size connections are ready
        self._pool.wait()
        logger.info(
            "Connection pool ready: %s:%s/%s (min=%d, max=%d)",
            self.config.host, self.config.port, self.config.name,
            POOL_MIN_SIZE, POOL_MAX_SIZE,
        )

    def close(self) -> None:
        """Release current thread's connection and shut down the pool."""
        self._release()
        if self._pool:
            self._pool.close()
            self._pool = None

    @property
    def conn(self) -> psycopg.Connection:
        """Get the current thread's connection, checking out from pool if needed.

        If the thread's connection has a failed transaction (INERROR state),
        it's automatically rolled back before reuse.
        """
        existing = getattr(self._local, "conn", None)
        if existing is not None and not existing.closed:
            # Auto-recover from failed transactions (e.g. uncaught exceptions
            # between execute and commit left the connection in INERROR)
            if existing.info.transaction_status == psycopg.pq.TransactionStatus.INERROR:
                logger.warning("Rolling back failed transaction on reused connection")
                existing.rollback()
            return existing

        # Check out a new connection from the pool
        if self._pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        self._local.conn = self._pool.getconn()
        return self._local.conn

    def _release(self) -> None:
        """Return the current thread's connection to the pool."""
        existing = getattr(self._local, "conn", None)
        if existing is not None and self._pool is not None:
            try:
                self._pool.putconn(existing)
            except Exception:
                logger.warning("Failed to return connection to pool", exc_info=True)
            self._local.conn = None

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
        """Commit the current transaction and return connection to pool."""
        self.conn.commit()
        self._release()

    def rollback(self) -> None:
        """Rollback the current transaction and return connection to pool."""
        self.conn.rollback()
        self._release()

    def release_if_held(self) -> None:
        """Release the current thread's connection if held with an open transaction.

        Call at API request boundaries to prevent connection pool exhaustion.
        Read-only endpoints don't call commit/rollback, leaving connections
        checked out with stale transactions. This cleans them up.

        No-op if no connection is held or if already released by commit/rollback.
        """
        existing = getattr(self._local, "conn", None)
        if existing is None or existing.closed:
            return
        ts = existing.info.transaction_status
        if ts in (
            psycopg.pq.TransactionStatus.INTRANS,
            psycopg.pq.TransactionStatus.INERROR,
        ):
            try:
                existing.rollback()
            except Exception:
                pass
            self._release()

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

    def reconcile_vector_dimensions(self, dimensions: int) -> None:
        """Resize vector columns if configured dimensions differ from schema.

        Handles backend switches (e.g. local 384-dim → Bedrock 1024-dim) by:
        1. Altering vector column types on memories and clusters
        2. Nulling existing embeddings (old dimensions are invalid)
        3. Clearing stale clusters
        4. Recreating the HNSW index

        No-op when dimensions already match.
        """
        row = self.execute_one("""
            SELECT atttypmod FROM pg_attribute
            WHERE attrelid = 'memories'::regclass
              AND attname = 'embedding'
        """)
        if row is None:
            logger.warning("Could not read embedding column metadata — skipping reconciliation")
            self.rollback()
            return

        current_dim = row["atttypmod"]
        if current_dim == dimensions:
            logger.info("Vector dimensions match configured value (%d) — no reconciliation needed", dimensions)
            self.rollback()
            return

        logger.info("Reconciling vector dimensions: %d → %d", current_dim, dimensions)

        # Drop index, null existing embeddings, then resize columns
        self.execute("DROP INDEX IF EXISTS idx_memories_embedding")
        self.execute("UPDATE memories SET embedding = NULL")
        self.execute(f"ALTER TABLE memories ALTER COLUMN embedding TYPE vector({dimensions})")
        self.execute("DELETE FROM cluster_members")
        self.execute("DELETE FROM clusters")
        self.execute(f"ALTER TABLE clusters ALTER COLUMN centroid TYPE vector({dimensions})")

        self.execute("DELETE FROM clustering_runs")

        # Recreate HNSW index
        self.execute(f"""
            CREATE INDEX idx_memories_embedding
            ON memories USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """)

        self.commit()
        logger.info(
            "Vector dimensions reconciled: %d → %d. "
            "Existing embeddings cleared — re-embed required.",
            current_dim, dimensions,
        )
