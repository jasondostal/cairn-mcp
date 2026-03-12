"""Integration tests with real PostgreSQL (ca-220, ca-221).

These tests require a running PostgreSQL instance with pgvector.
They create a temporary test database, run migrations, and clean up.

Run locally: pytest tests/test_integration_postgres.py -v
CI: runs with a Postgres service container (see build.yml).

Skipped automatically if the database is unreachable.
"""

import os
import uuid

import pytest

# Connection params — CI sets these via env; local defaults to cairn-db on localhost
_PG_HOST = os.getenv("CAIRN_TEST_DB_HOST", "localhost")
_PG_PORT = int(os.getenv("CAIRN_TEST_DB_PORT", "5432"))
_PG_USER = os.getenv("CAIRN_TEST_DB_USER", "cairn")
_PG_PASS = os.getenv("CAIRN_TEST_DB_PASS", "cairn-dev-password")
_PG_MAINTENANCE_DB = os.getenv("CAIRN_TEST_DB_NAME", "cairn")  # used to create test db


def _pg_available() -> bool:
    """Check if Postgres is reachable."""
    try:
        import psycopg
        with psycopg.connect(
            f"postgresql://{_PG_USER}:{_PG_PASS}@{_PG_HOST}:{_PG_PORT}/{_PG_MAINTENANCE_DB}",
            autocommit=True,
        ) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _pg_available(),
    reason="PostgreSQL not reachable — skipping integration tests",
)


@pytest.fixture(scope="module")
def test_db_name():
    """Create a temporary test database and drop it after tests."""
    import psycopg

    db_name = f"cairn_test_{uuid.uuid4().hex[:8]}"

    # Create test database
    with psycopg.connect(
        f"postgresql://{_PG_USER}:{_PG_PASS}@{_PG_HOST}:{_PG_PORT}/{_PG_MAINTENANCE_DB}",
        autocommit=True,
    ) as conn:
        conn.execute(f"CREATE DATABASE {db_name}")
        # Enable pgvector extension
    with psycopg.connect(
        f"postgresql://{_PG_USER}:{_PG_PASS}@{_PG_HOST}:{_PG_PORT}/{db_name}",
        autocommit=True,
    ) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    yield db_name

    # Cleanup: drop test database
    with psycopg.connect(
        f"postgresql://{_PG_USER}:{_PG_PASS}@{_PG_HOST}:{_PG_PORT}/{_PG_MAINTENANCE_DB}",
        autocommit=True,
    ) as conn:
        # Terminate any remaining connections
        conn.execute(f"""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '{db_name}' AND pid <> pg_backend_pid()
        """)
        conn.execute(f"DROP DATABASE IF EXISTS {db_name}")


@pytest.fixture(scope="module")
def db(test_db_name):
    """Provide a connected Database instance with migrations applied."""
    from cairn.config import DatabaseConfig
    from cairn.storage.database import Database

    config = DatabaseConfig(
        host=_PG_HOST,
        port=_PG_PORT,
        name=test_db_name,
        user=_PG_USER,
        password=_PG_PASS,
    )
    database = Database(config)
    database.connect()
    database.run_migrations()
    yield database
    database.close()


# ---------------------------------------------------------------------------
# ca-220: Service assembly integration test
# ---------------------------------------------------------------------------


class TestServiceAssembly:
    """Verify that create_services() wires up correctly against a real DB."""

    def test_create_services_returns_non_none_critical(self, db):
        """After create_services(), critical fields must be non-None."""
        from cairn.config import Config
        from cairn.core.services import create_services

        config = Config(
            enrichment_enabled=False,
            transport="stdio",
        )
        svc = create_services(config=config, db=db)

        assert svc.db is db
        assert svc.memory_store is not None
        assert svc.search_engine is not None
        assert svc.cluster_engine is not None
        assert svc.project_manager is not None
        assert svc.work_item_manager is not None
        assert svc.event_bus is not None

    def test_create_services_memory_store_uses_same_db(self, db):
        """MemoryStore should use the same DB instance passed to create_services."""
        from cairn.config import Config
        from cairn.core.services import create_services

        config = Config(enrichment_enabled=False)
        svc = create_services(config=config, db=db)

        assert svc.memory_store.db is db

    def test_project_crud(self, db):
        """Basic project create/read through get_or_create_project."""
        from cairn.core.utils import get_or_create_project, get_project

        name = f"test-project-{uuid.uuid4().hex[:6]}"
        project_id = get_or_create_project(db, name)

        assert project_id > 0

        # Read back
        fetched_id = get_project(db, name)
        assert fetched_id == project_id

    def test_db_migrations_are_idempotent(self, db):
        """Running migrations twice should not raise."""
        db.run_migrations()
        # Verify a core table exists
        row = db.execute_one(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'memories'"
        )
        assert row is not None


# ---------------------------------------------------------------------------
# ca-221: Round-trip memory store + search
# ---------------------------------------------------------------------------


class TestMemoryRoundTrip:
    """Store a memory and retrieve it via search — full round-trip."""

    @pytest.fixture(autouse=True)
    def _setup(self, db):
        """Set up embedding engine and memory store for each test."""
        from cairn.config import Config
        from cairn.core.services import create_services

        config = Config(enrichment_enabled=False)
        svc = create_services(config=config, db=db)
        self.db = db
        self.memory_store = svc.memory_store
        self.search_engine = svc.search_engine

    def test_store_and_retrieve_by_id(self):
        """Store a memory and fetch it by ID."""
        result = self.memory_store.store(
            content="Integration test memory — unique canary phrase xylophone42",
            memory_type="note",
            importance=0.7,
            project="test-roundtrip",
        )

        memory_id = result["id"]
        assert memory_id > 0

        # Retrieve by ID via recall()
        recalled = self.memory_store.recall([memory_id])
        assert len(recalled) == 1
        assert recalled[0]["id"] == memory_id
        assert "xylophone42" in recalled[0]["content"]

    def test_store_and_search_semantic(self):
        """Store a memory and find it via semantic search."""
        canary = f"cairn-integration-{uuid.uuid4().hex[:8]}"
        self.memory_store.store(
            content=f"The {canary} protocol handles distributed consensus",
            memory_type="note",
            importance=0.8,
            project="test-roundtrip",
        )

        results = self.search_engine.search(
            query=f"{canary} distributed consensus",
            project="test-roundtrip",
            limit=5,
            include_full=True,
        )

        # Should find our memory in results (content or summary)
        found = any(
            canary in (r.get("content") or r.get("summary") or "")
            for r in results
        )
        assert found, f"Canary '{canary}' not found in search results: {results}"

    def test_store_with_tags_and_search(self):
        """Store with tags and verify tags are present in results."""
        tag = f"tag-{uuid.uuid4().hex[:6]}"
        self.memory_store.store(
            content=f"Tagged memory for {tag} filter test",
            memory_type="decision",
            importance=0.5,
            project="test-roundtrip",
            tags=[tag],
        )

        results = self.search_engine.search(
            query=f"{tag} tagged memory filter",
            project="test-roundtrip",
            limit=5,
            include_full=True,
        )
        assert len(results) >= 1
        assert any(tag in r.get("tags", []) for r in results)

    def test_store_and_deactivate(self):
        """Store, deactivate, verify it no longer appears in active queries."""
        result = self.memory_store.store(
            content="Memory to be deactivated in integration test",
            memory_type="note",
            importance=0.3,
            project="test-roundtrip",
        )
        memory_id = result["id"]

        # Deactivate
        self.memory_store.modify(memory_id, action="inactivate")

        # Should not appear in search
        results = self.search_engine.search(
            query="deactivated integration test",
            project="test-roundtrip",
            limit=10,
        )
        found = any(r.get("id") == memory_id for r in results)
        assert not found, "Deactivated memory should not appear in search results"

    def test_memory_types_are_searchable(self):
        """Different memory types should be searchable via type filter."""
        canary = f"typetest-{uuid.uuid4().hex[:6]}"
        for mtype in ("note", "decision", "learning"):
            self.memory_store.store(
                content=f"{canary} type filter test — {mtype} memory content",
                memory_type=mtype,
                importance=0.5,
                project="test-roundtrip",
            )

        results = self.search_engine.search(
            query=f"{canary} type filter test",
            project="test-roundtrip",
            memory_type="decision",
            limit=10,
        )
        assert len(results) >= 1
        assert all(r.get("memory_type") == "decision" for r in results)
