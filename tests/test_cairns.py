"""Tests for CairnManager — episodic session markers."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, call

from cairn.config import LLMCapabilities
from cairn.core.cairns import CairnManager


def _make_db():
    """Create a mock Database."""
    db = MagicMock()
    # Default: get_or_create_project returns project_id=1
    db.execute_one.return_value = {"id": 1}
    return db


def _make_stone(id, content="test content", memory_type="note", summary=None):
    """Create a mock stone (memory) row."""
    return {
        "id": id,
        "content": content,
        "summary": summary or content[:50],
        "memory_type": memory_type,
        "importance": 0.5,
        "tags": [],
        "auto_tags": [],
        "created_at": datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
    }


class TestCairnSet:
    """Tests for CairnManager.set()."""

    def test_set_creates_cairn_with_stones(self):
        """Setting a cairn creates the record and links stones."""
        db = _make_db()
        stones = [_make_stone(1), _make_stone(2), _make_stone(3)]

        # Sequence: get_or_create_project, check existing, insert cairn
        db.execute_one.side_effect = [
            {"id": 1},   # project lookup
            None,         # no existing cairn
            {             # INSERT RETURNING
                "id": 10,
                "title": "Session: test-session",
                "narrative": None,
                "memory_count": 3,
                "started_at": datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
                "set_at": datetime(2026, 2, 8, 14, 0, 0, tzinfo=timezone.utc),
            },
        ]
        # execute: stones query, digests query (empty), UPDATE memories
        db.execute.side_effect = [stones, [], None]

        manager = CairnManager(db)
        result = manager.set("test-project", "test-session")

        assert result["id"] == 10
        assert result["memory_count"] == 3
        assert result["title"] == "Session: test-session"
        assert result["narrative"] is None
        db.commit.assert_called_once()

    def test_set_returns_existing_cairn(self):
        """Setting a cairn for an existing session returns existing info."""
        db = _make_db()
        db.execute_one.side_effect = [
            {"id": 1},  # project lookup
            {           # existing cairn found
                "id": 5,
                "has_events": False,
                "title": "Existing Session",
                "narrative": "Already done.",
                "memory_count": 2,
            },
        ]

        manager = CairnManager(db)
        result = manager.set("test-project", "test-session")

        assert result["status"] == "already_exists"
        assert result["id"] == 5

    def test_set_with_llm_synthesizes_narrative(self):
        """When LLM is available, cairn gets title and narrative."""
        db = _make_db()
        stones = [_make_stone(1, "Decided to use PostgreSQL"), _make_stone(2, "Implemented connection pool")]

        db.execute_one.side_effect = [
            {"id": 1},   # project lookup
            None,         # no existing cairn
            {             # INSERT RETURNING
                "id": 10,
                "title": "PostgreSQL Integration and Connection Pooling",
                "narrative": "The session focused on database setup.",
                "memory_count": 2,
                "started_at": datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
                "set_at": datetime(2026, 2, 8, 14, 0, 0, tzinfo=timezone.utc),
            },
        ]
        db.execute.side_effect = [stones, [], None]  # stones, no digests, UPDATE

        llm = MagicMock()
        llm.generate.return_value = '{"title": "PostgreSQL Integration and Connection Pooling", "narrative": "The session focused on database setup."}'

        caps = LLMCapabilities(session_synthesis=True)
        manager = CairnManager(db, llm=llm, capabilities=caps)
        result = manager.set("test-project", "test-session")

        assert result["id"] == 10
        llm.generate.assert_called_once()

    def test_set_graceful_degradation_no_llm(self):
        """Without LLM, cairn is created with fallback title and no narrative."""
        db = _make_db()
        stones = [_make_stone(1)]

        db.execute_one.side_effect = [
            {"id": 1},
            None,
            {
                "id": 10,
                "title": "Session: my-session",
                "narrative": None,
                "memory_count": 1,
                "started_at": datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
                "set_at": datetime(2026, 2, 8, 14, 0, 0, tzinfo=timezone.utc),
            },
        ]
        db.execute.side_effect = [stones, [], None]  # stones, no digests, UPDATE

        manager = CairnManager(db)  # no LLM
        result = manager.set("test-project", "my-session")

        assert result["id"] == 10
        assert result["narrative"] is None
        assert "Session:" in result["title"]

    def test_set_empty_session(self):
        """Setting a cairn with no stones and no digests skips."""
        db = _make_db()

        db.execute_one.side_effect = [
            {"id": 1},
            None,
        ]
        db.execute.side_effect = [[], []]  # no stones, no digests

        manager = CairnManager(db)
        result = manager.set("test-project", "ghost-session")

        assert result.get("skipped") is True

    def test_set_with_events(self):
        """Events (hook data) are passed through to the cairn."""
        db = _make_db()

        db.execute_one.side_effect = [
            {"id": 1},
            None,
            {
                "id": 10,
                "title": "Session: hook-session",
                "narrative": None,
                "memory_count": 0,
                "started_at": datetime(2026, 2, 8, 14, 0, 0, tzinfo=timezone.utc),
                "set_at": datetime(2026, 2, 8, 14, 0, 0, tzinfo=timezone.utc),
            },
        ]
        db.execute.side_effect = [[], []]  # no stones, no digests

        manager = CairnManager(db)
        events = [{"type": "tool_call", "tool": "store", "ts": "2026-02-08T12:00:00Z"}]
        result = manager.set("test-project", "hook-session", events=events)

        assert result["id"] == 10
        # Verify events were passed in the INSERT call
        insert_call = db.execute_one.call_args_list[2]
        assert insert_call[0][1][4] is not None  # events param is not None

    def test_set_with_events_triggers_llm_even_without_stones(self):
        """When events (motes) are provided but no stones exist, LLM synthesis still runs."""
        db = _make_db()

        db.execute_one.side_effect = [
            {"id": 1},   # project lookup
            None,         # no existing cairn
            {             # INSERT RETURNING
                "id": 10,
                "title": "Hook Session: Codebase Exploration",
                "narrative": "The session explored the codebase via tool calls.",
                "memory_count": 0,
                "started_at": datetime(2026, 2, 8, 14, 0, 0, tzinfo=timezone.utc),
                "set_at": datetime(2026, 2, 8, 14, 0, 0, tzinfo=timezone.utc),
            },
        ]
        db.execute.side_effect = [[], []]  # no stones, no digests

        llm = MagicMock()
        llm.generate.return_value = '{"title": "Hook Session: Codebase Exploration", "narrative": "The session explored the codebase via tool calls."}'

        caps = LLMCapabilities(session_synthesis=True)
        manager = CairnManager(db, llm=llm, capabilities=caps)

        events = [
            {"type": "session_start", "ts": "2026-02-08T12:00:00Z", "project": "test-project", "session_name": "hook-session"},
            {"type": "tool_call", "tool": "Read", "ts": "2026-02-08T12:01:00Z", "path": "src/main.py"},
            {"type": "tool_call", "tool": "Grep", "ts": "2026-02-08T12:02:00Z"},
            {"type": "session_end", "ts": "2026-02-08T12:05:00Z", "reason": "user_exit"},
        ]
        result = manager.set("test-project", "hook-session", events=events)

        assert result["id"] == 10
        # LLM was called even though there were 0 stones
        llm.generate.assert_called_once()
        # Verify the messages passed to LLM contain mote-aware content
        messages = llm.generate.call_args[0][0]
        assert "Mote timeline" in messages[1]["content"]
        assert "tool_call" in messages[1]["content"]

    def test_set_with_events_and_stones_uses_mote_prompt(self):
        """When both events and stones are present, mote-aware prompt is used."""
        db = _make_db()
        stones = [_make_stone(1, "Decided to use PostgreSQL")]

        db.execute_one.side_effect = [
            {"id": 1},
            None,
            {
                "id": 10,
                "title": "Database Setup with PostgreSQL",
                "narrative": "The session set up PostgreSQL.",
                "memory_count": 1,
                "started_at": datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
                "set_at": datetime(2026, 2, 8, 14, 0, 0, tzinfo=timezone.utc),
            },
        ]
        db.execute.side_effect = [stones, [], None]  # stones, no digests, UPDATE

        llm = MagicMock()
        llm.generate.return_value = '{"title": "Database Setup with PostgreSQL", "narrative": "The session set up PostgreSQL."}'

        caps = LLMCapabilities(session_synthesis=True)
        manager = CairnManager(db, llm=llm, capabilities=caps)

        events = [
            {"type": "tool_call", "tool": "Read", "ts": "2026-02-08T12:01:00Z", "path": "docker-compose.yml"},
        ]
        result = manager.set("test-project", "test-session", events=events)

        llm.generate.assert_called_once()
        messages = llm.generate.call_args[0][0]
        # System prompt should be the mote-aware variant
        assert "Motes" in messages[0]["content"]
        # User content should have both stones and motes
        assert "Stones (chronological):" in messages[1]["content"]
        assert "Mote timeline" in messages[1]["content"]


class TestCairnSetWithDigests:
    """Tests for CairnManager.set() with Pipeline v2 digests."""

    def test_set_uses_digests_when_available(self):
        """When session_events have digests, cairn uses digest narrative prompt."""
        db = _make_db()
        stones = [_make_stone(1, "Decided to use streaming pipeline")]

        digests = [
            {"batch_number": 0, "digest": "Explored the codebase structure and read key configuration files."},
            {"batch_number": 1, "digest": "Edited the server module to add event ingestion endpoint."},
        ]

        db.execute_one.side_effect = [
            {"id": 1},   # project lookup
            None,         # no existing cairn
            {             # INSERT RETURNING
                "id": 10,
                "title": "Implemented Streaming Event Pipeline",
                "narrative": "The session implemented a streaming event pipeline.",
                "memory_count": 1,
                "started_at": datetime(2026, 2, 9, 12, 0, 0, tzinfo=timezone.utc),
                "set_at": datetime(2026, 2, 9, 14, 0, 0, tzinfo=timezone.utc),
            },
        ]
        # execute: stones, digests, UPDATE memories
        db.execute.side_effect = [stones, digests, None]

        llm = MagicMock()
        llm.generate.return_value = '{"title": "Implemented Streaming Event Pipeline", "narrative": "The session implemented a streaming event pipeline."}'

        caps = LLMCapabilities(session_synthesis=True)
        manager = CairnManager(db, llm=llm, capabilities=caps)
        result = manager.set("test-project", "test-session")

        assert result["id"] == 10
        llm.generate.assert_called_once()
        # Verify the digest narrative prompt was used (contains "Work log digests")
        messages = llm.generate.call_args[0][0]
        assert "digests" in messages[0]["content"].lower() or "Work log digests" in messages[1]["content"]

    def test_set_falls_back_to_raw_events_when_no_digests(self):
        """When no digests exist, cairn falls back to raw events (Pipeline v1)."""
        db = _make_db()
        stones = [_make_stone(1)]

        db.execute_one.side_effect = [
            {"id": 1},   # project lookup
            None,         # no existing cairn
            {             # INSERT RETURNING
                "id": 10,
                "title": "Session: test-session",
                "narrative": "Explored the codebase.",
                "memory_count": 1,
                "started_at": datetime(2026, 2, 9, 12, 0, 0, tzinfo=timezone.utc),
                "set_at": datetime(2026, 2, 9, 14, 0, 0, tzinfo=timezone.utc),
            },
        ]
        # No digests available
        db.execute.side_effect = [stones, [], None]  # stones, empty digests, UPDATE

        events = [{"type": "tool_call", "tool": "Read", "ts": "2026-02-09T12:00:00Z"}]

        llm = MagicMock()
        llm.generate.return_value = '{"title": "Session: test-session", "narrative": "Explored the codebase."}'

        caps = LLMCapabilities(session_synthesis=True)
        manager = CairnManager(db, llm=llm, capabilities=caps)
        result = manager.set("test-project", "test-session", events=events)

        assert result["id"] == 10
        llm.generate.assert_called_once()
        # Verify the mote timeline prompt was used (Pipeline v1 fallback)
        messages = llm.generate.call_args[0][0]
        assert "Mote timeline" in messages[1]["content"] or "Motes" in messages[0]["content"]


class TestCairnStack:
    """Tests for CairnManager.stack()."""

    def test_stack_returns_ordered_cairns(self):
        """Stack returns cairns newest first."""
        db = _make_db()
        db.execute.return_value = [
            {
                "id": 3, "session_name": "session-3", "title": "Third",
                "narrative": "Third session", "memory_count": 5,
                "project": "test-project",
                "started_at": datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
                "set_at": datetime(2026, 2, 8, 14, 0, 0, tzinfo=timezone.utc),
                "is_compressed": False,
            },
            {
                "id": 2, "session_name": "session-2", "title": "Second",
                "narrative": "Second session", "memory_count": 3,
                "project": "test-project",
                "started_at": datetime(2026, 2, 7, 12, 0, 0, tzinfo=timezone.utc),
                "set_at": datetime(2026, 2, 7, 14, 0, 0, tzinfo=timezone.utc),
                "is_compressed": False,
            },
        ]

        manager = CairnManager(db)
        result = manager.stack("test-project")

        assert len(result) == 2
        assert result[0]["id"] == 3
        assert result[1]["id"] == 2

    def test_stack_respects_limit(self):
        """Stack passes limit to query."""
        db = _make_db()
        db.execute.return_value = []

        manager = CairnManager(db)
        manager.stack("test-project", limit=5)

        # Verify limit was passed in the query params
        stack_call = db.execute.call_args_list[0]
        assert stack_call[0][1] == (1, 5)


class TestCairnGet:
    """Tests for CairnManager.get()."""

    def test_get_returns_full_detail_with_stones(self):
        """Get returns cairn detail and linked stones."""
        db = _make_db()

        db.execute_one.return_value = {
            "id": 10, "session_name": "test-session", "title": "Test Cairn",
            "narrative": "A narrative.", "events": None, "memory_count": 2,
            "started_at": datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
            "set_at": datetime(2026, 2, 8, 14, 0, 0, tzinfo=timezone.utc),
            "is_compressed": False, "project": "test-project",
        }
        db.execute.return_value = [
            {
                "id": 1, "summary": "First stone", "content": "First stone content",
                "memory_type": "decision", "importance": 0.8, "tags": ["db"],
                "created_at": datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
            },
            {
                "id": 2, "summary": "Second stone", "content": "Second stone content",
                "memory_type": "note", "importance": 0.5, "tags": [],
                "created_at": datetime(2026, 2, 8, 13, 0, 0, tzinfo=timezone.utc),
            },
        ]

        manager = CairnManager(db)
        result = manager.get(10)

        assert result["id"] == 10
        assert result["title"] == "Test Cairn"
        assert result["narrative"] == "A narrative."
        assert len(result["stones"]) == 2
        assert result["stones"][0]["memory_type"] == "decision"

    def test_get_raises_on_not_found(self):
        """Get raises ValueError for unknown cairn ID."""
        db = _make_db()
        db.execute_one.return_value = None

        manager = CairnManager(db)
        try:
            manager.get(999)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "999" in str(e)


class TestCairnCompress:
    """Tests for CairnManager.compress()."""

    def test_compress_clears_events(self):
        """Compress sets is_compressed and clears events."""
        db = _make_db()
        db.execute_one.return_value = {"id": 10, "is_compressed": False}

        manager = CairnManager(db)
        result = manager.compress(10)

        assert result["status"] == "compressed"
        db.commit.assert_called_once()

    def test_compress_idempotent(self):
        """Compressing an already-compressed cairn returns status."""
        db = _make_db()
        db.execute_one.return_value = {"id": 10, "is_compressed": True}

        manager = CairnManager(db)
        result = manager.compress(10)

        assert result["status"] == "already_compressed"
        db.commit.assert_not_called()

    def test_compress_raises_on_not_found(self):
        """Compress raises ValueError for unknown cairn ID."""
        db = _make_db()
        db.execute_one.return_value = None

        manager = CairnManager(db)
        try:
            manager.compress(999)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "999" in str(e)
