"""Corpus loading, eval DB creation, and memory insertion.

Handles:
- Loading corpus.json and validating schema
- Creating per-model eval databases with patched vector dimensions
- Inserting corpus memories with embeddings
- Maintaining corpus_id -> db_id mapping
"""

import json
import logging
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from cairn.embedding.engine import EmbeddingEngine

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
MIGRATIONS_DIR = Path(__file__).parent.parent / "cairn" / "storage" / "migrations"

REQUIRED_MEMORY_FIELDS = {"id", "content", "memory_type", "importance", "tags"}


def load_corpus(path: Path | None = None) -> dict:
    """Load and validate corpus.json.

    Returns the full corpus dict with metadata and memories list.
    Raises ValueError on schema violations.
    """
    path = path or DATA_DIR / "corpus.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Corpus file not found: {path}\n"
            "Run 'python -m eval.corpus_export' to generate it."
        )

    corpus = json.loads(path.read_text())

    if "memories" not in corpus:
        raise ValueError("Corpus must contain 'memories' key")
    if not corpus["memories"]:
        raise ValueError("Corpus must contain at least one memory")

    # Validate each memory
    ids_seen = set()
    for mem in corpus["memories"]:
        missing = REQUIRED_MEMORY_FIELDS - set(mem.keys())
        if missing:
            raise ValueError(f"Memory {mem.get('id', '?')} missing fields: {missing}")
        if mem["id"] in ids_seen:
            raise ValueError(f"Duplicate memory ID: {mem['id']}")
        ids_seen.add(mem["id"])

    logger.info("Loaded corpus: %d memories", len(corpus["memories"]))
    return corpus


def create_eval_db(
    admin_dsn: str,
    db_name: str,
    vector_dims: int,
) -> None:
    """Create an eval database with patched vector dimensions.

    1. Connect with autocommit (required for CREATE DATABASE)
    2. Create the eval database
    3. Read migration SQL files, replace vector(384) -> vector(N)
    4. Execute patched DDL
    """
    # Create database (requires autocommit)
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        # Terminate existing connections before drop
        conn.execute("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
        """, (db_name,))
        # Drop if exists for clean state
        conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
        conn.execute(f"CREATE DATABASE {db_name}")
        logger.info("Created eval database: %s", db_name)

    # Build DSN for the new database
    # Replace the database name in the admin DSN
    eval_dsn = _replace_dbname(admin_dsn, db_name)

    # Apply patched migrations
    with psycopg.connect(eval_dsn) as conn:
        for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            sql = migration_file.read_text()
            # Patch vector dimensions
            sql = sql.replace("vector(384)", f"vector({vector_dims})")
            conn.execute(sql)
            logger.info("Applied migration: %s (dims=%d)", migration_file.name, vector_dims)
        conn.commit()


def drop_eval_db(admin_dsn: str, db_name: str) -> None:
    """Drop an eval database."""
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        # Terminate existing connections first
        conn.execute("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
        """, (db_name,))
        conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
        logger.info("Dropped eval database: %s", db_name)


def insert_corpus(
    eval_dsn: str,
    corpus: dict,
    embedding_engine: EmbeddingEngine,
) -> dict[str, int]:
    """Insert corpus memories into an eval database.

    Embeds all content with the given engine, inserts via raw SQL
    (bypasses MemoryStore.store() to avoid re-enrichment).

    Returns:
        Mapping of corpus_id -> database_id
    """
    memories = corpus["memories"]
    contents = [m["content"] for m in memories]

    logger.info("Embedding %d memories...", len(contents))
    vectors = embedding_engine.embed_batch(contents)

    id_map = {}
    with psycopg.connect(eval_dsn, row_factory=dict_row) as conn:
        for mem, vector in zip(memories, vectors):
            # Ensure project exists
            conn.execute(
                "INSERT INTO projects (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                (mem.get("project", "general"),),
            )
            project_row = conn.execute(
                "SELECT id FROM projects WHERE name = %s",
                (mem.get("project", "general"),),
            ).fetchone()
            project_id = project_row["id"] if project_row else None

            row = conn.execute(
                """
                INSERT INTO memories (
                    content, memory_type, importance, tags, auto_tags,
                    embedding, project_id, session_name, is_active, entities
                ) VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, true, %s)
                RETURNING id
                """,
                (
                    mem["content"],
                    mem["memory_type"],
                    mem["importance"],
                    mem.get("tags", []),
                    mem.get("auto_tags", []),
                    str(vector),
                    project_id,
                    mem.get("session_name", ""),
                    mem.get("entities", []),
                ),
            ).fetchone()

            id_map[mem["id"]] = row["id"]

        conn.commit()

    logger.info("Inserted %d memories, id_map built", len(id_map))
    return id_map


def _replace_dbname(dsn: str, new_dbname: str) -> str:
    """Replace the database name in a PostgreSQL DSN.

    Handles: postgresql://user:pass@host:port/olddb -> .../newdb
    """
    # Split on last '/' and replace
    base = dsn.rsplit("/", 1)[0]
    return f"{base}/{new_dbname}"
