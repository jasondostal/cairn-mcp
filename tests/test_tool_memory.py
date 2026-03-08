"""Tests for MCP memory tools: store, search, recall round-trip.

Tests the tool functions registered inside cairn.tools.memory.register()
by using a MockMCP that captures decorated tool functions.
"""

import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from cairn.tools.memory import register


# ---------------------------------------------------------------------------
# MockMCP: captures tool functions registered via @mcp.tool()
# ---------------------------------------------------------------------------

class MockMCP:
    """Captures tool functions registered via @mcp.tool() decorator."""

    def __init__(self):
        self.tools: dict[str, callable] = {}

    def tool(self, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


@dataclass
class MockBudgetConfig:
    search: int = 0  # 0 = disabled (no budget cap)
    recall: int = 0


@dataclass
class MockAuthConfig:
    enabled: bool = False


@dataclass
class MockConfig:
    budget: MockBudgetConfig = None
    auth: MockAuthConfig = None

    def __post_init__(self):
        if self.budget is None:
            self.budget = MockBudgetConfig()
        if self.auth is None:
            self.auth = MockAuthConfig()


def _make_svc(**overrides):
    """Build a mock Services with sensible defaults for memory tools."""
    svc = MagicMock()
    svc.config = MockConfig()
    svc.event_bus = None  # disable event publishing by default
    svc.db = MagicMock()
    for key, val in overrides.items():
        setattr(svc, key, val)
    return svc


def _register_tools(svc):
    """Register memory tools and return the tool dict."""
    mcp = MockMCP()
    register(mcp, svc)
    return mcp.tools


# ---------------------------------------------------------------------------
# store() tool tests
# ---------------------------------------------------------------------------

class TestStoreRoundTrip:
    """Test store tool validates, delegates to svc.memory_store.store()."""

    def test_store_calls_memory_store(self):
        svc = _make_svc()
        svc.memory_store.store.return_value = {"id": 42, "status": "stored"}
        tools = _register_tools(svc)

        result = asyncio.run(tools["store"](
            content="Architecture decision: use PostgreSQL",
            project="cairn",
            memory_type="decision",
            importance=0.8,
        ))

        assert result == {"id": 42, "status": "stored"}
        svc.memory_store.store.assert_called_once()
        call_kwargs = svc.memory_store.store.call_args.kwargs
        assert call_kwargs["content"] == "Architecture decision: use PostgreSQL"
        assert call_kwargs["project"] == "cairn"
        assert call_kwargs["memory_type"] == "decision"
        assert call_kwargs["importance"] == 0.8

    def test_store_passes_optional_fields(self):
        svc = _make_svc()
        svc.memory_store.store.return_value = {"id": 1}
        tools = _register_tools(svc)

        asyncio.run(tools["store"](
            content="test content",
            project="proj",
            tags=["infra", "deploy"],
            session_name="sprint-1",
            related_files=["/path/to/file.py"],
            related_ids=[10, 20],
            author="user",
        ))

        call_kwargs = svc.memory_store.store.call_args.kwargs
        assert call_kwargs["tags"] == ["infra", "deploy"]
        assert call_kwargs["session_name"] == "sprint-1"
        assert call_kwargs["related_files"] == ["/path/to/file.py"]
        assert call_kwargs["related_ids"] == [10, 20]
        assert call_kwargs["author"] == "user"

    def test_store_validates_empty_content(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["store"](content="", project="cairn"))

        assert "error" in result
        assert "content" in result["error"].lower()
        svc.memory_store.store.assert_not_called()

    def test_store_validates_empty_project(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["store"](content="stuff", project=""))

        assert "error" in result
        assert "project" in result["error"].lower()

    def test_store_validates_bad_memory_type(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["store"](
            content="stuff", project="p", memory_type="banana",
        ))

        assert "error" in result
        assert "memory_type" in result["error"]

    def test_store_validates_importance_range(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["store"](
            content="stuff", project="p", importance=1.5,
        ))

        assert "error" in result
        assert "importance" in result["error"]

    def test_store_internal_error_caught(self):
        svc = _make_svc()
        svc.memory_store.store.side_effect = RuntimeError("db exploded")
        tools = _register_tools(svc)

        result = asyncio.run(tools["store"](
            content="stuff", project="cairn",
        ))

        assert "error" in result
        assert "Internal error" in result["error"]


# ---------------------------------------------------------------------------
# search() tool tests
# ---------------------------------------------------------------------------

class TestSearchRoundTrip:
    """Test search tool validates, calls svc.search_engine.search()."""

    def test_search_returns_results(self):
        svc = _make_svc()
        svc.search_engine.search.return_value = [
            {"id": 1, "summary": "deploy procedure"},
            {"id": 2, "summary": "db migration steps"},
        ]
        svc.search_engine.assess_confidence.return_value = None
        tools = _register_tools(svc)

        result = asyncio.run(tools["search"](query="deploy"))

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == 1

    def test_search_passes_all_params(self):
        svc = _make_svc()
        svc.search_engine.search.return_value = []
        svc.search_engine.assess_confidence.return_value = None
        tools = _register_tools(svc)

        asyncio.run(tools["search"](
            query="deploy",
            project="cairn",
            memory_type="decision",
            search_mode="keyword",
            limit=5,
            include_full=True,
            ephemeral=False,
        ))

        call_kwargs = svc.search_engine.search.call_args.kwargs
        assert call_kwargs["query"] == "deploy"
        assert call_kwargs["project"] == "cairn"
        assert call_kwargs["memory_type"] == "decision"
        assert call_kwargs["search_mode"] == "keyword"
        assert call_kwargs["limit"] == 5
        assert call_kwargs["include_full"] is True
        assert call_kwargs["ephemeral"] is False

    def test_search_validates_empty_query(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["search"](query=""))

        assert isinstance(result, list)
        assert "error" in result[0]
        assert "query" in result[0]["error"].lower()

    def test_search_validates_bad_search_mode(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["search"](query="test", search_mode="magic"))

        assert isinstance(result, list)
        assert "error" in result[0]
        assert "search_mode" in result[0]["error"]

    def test_search_with_budget_cap(self):
        """When budget > 0, apply_list_budget is called."""
        svc = _make_svc()
        svc.config.budget.search = 100  # small budget
        svc.search_engine.search.return_value = [
            {"id": i, "summary": "x" * 500} for i in range(20)
        ]
        svc.search_engine.assess_confidence.return_value = None
        tools = _register_tools(svc)

        result = asyncio.run(tools["search"](query="test"))

        # With a tiny budget, some results should be capped
        assert isinstance(result, list)
        assert len(result) <= 21  # at most 20 + overflow marker

    def test_search_publishes_event(self):
        event_bus = MagicMock()
        svc = _make_svc(event_bus=event_bus)
        svc.search_engine.search.return_value = [{"id": 1, "summary": "test"}]
        svc.search_engine.assess_confidence.return_value = None
        tools = _register_tools(svc)

        asyncio.run(tools["search"](query="test query"))

        event_bus.publish.assert_called_once()
        call_kwargs = event_bus.publish.call_args.kwargs
        assert call_kwargs["event_type"] == "search.executed"
        assert call_kwargs["payload"]["query"] == "test query"

    def test_search_confidence_gating(self):
        svc = _make_svc()
        svc.search_engine.search.return_value = [{"id": 1, "summary": "test"}]
        svc.search_engine.assess_confidence.return_value = {"level": "high", "score": 0.95}
        tools = _register_tools(svc)

        result = asyncio.run(tools["search"](query="test"))

        assert "results" in result
        assert "confidence" in result

    def test_search_internal_error_caught(self):
        svc = _make_svc()
        svc.search_engine.search.side_effect = RuntimeError("search exploded")
        tools = _register_tools(svc)

        result = asyncio.run(tools["search"](query="test"))

        assert isinstance(result, list)
        assert "Internal error" in result[0]["error"]


# ---------------------------------------------------------------------------
# recall() tool tests
# ---------------------------------------------------------------------------

class TestRecallRoundTrip:
    """Test recall tool validates IDs, calls svc.memory_store.recall()."""

    def test_recall_returns_full_content(self):
        svc = _make_svc()
        svc.memory_store.recall.return_value = [
            {"id": 1, "content": "full memory content here"},
        ]
        tools = _register_tools(svc)

        result = asyncio.run(tools["recall"](ids=[1]))

        assert result == [{"id": 1, "content": "full memory content here"}]
        svc.memory_store.recall.assert_called_once_with([1])

    def test_recall_multiple_ids(self):
        svc = _make_svc()
        svc.memory_store.recall.return_value = [
            {"id": 1, "content": "a"},
            {"id": 2, "content": "b"},
        ]
        tools = _register_tools(svc)

        result = asyncio.run(tools["recall"](ids=[1, 2]))

        assert len(result) == 2
        svc.memory_store.recall.assert_called_once_with([1, 2])

    def test_recall_empty_ids_error(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["recall"](ids=[]))

        assert isinstance(result, list)
        assert "error" in result[0]
        assert "empty" in result[0]["error"]

    def test_recall_too_many_ids_error(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["recall"](ids=list(range(1, 15))))

        assert isinstance(result, list)
        assert "error" in result[0]
        assert "Maximum" in result[0]["error"]

    def test_recall_with_budget_cap(self):
        svc = _make_svc()
        svc.config.budget.recall = 50  # tiny budget
        svc.memory_store.recall.return_value = [
            {"id": i, "content": "x" * 2000} for i in range(5)
        ]
        tools = _register_tools(svc)

        result = asyncio.run(tools["recall"](ids=[1, 2, 3, 4, 5]))

        assert isinstance(result, list)

    def test_recall_publishes_event(self):
        event_bus = MagicMock()
        svc = _make_svc(event_bus=event_bus)
        svc.memory_store.recall.return_value = [{"id": 1, "content": "test"}]
        tools = _register_tools(svc)

        asyncio.run(tools["recall"](ids=[1]))

        event_bus.publish.assert_called_once()
        call_kwargs = event_bus.publish.call_args.kwargs
        assert call_kwargs["event_type"] == "memory.recalled"

    def test_recall_internal_error_caught(self):
        svc = _make_svc()
        svc.memory_store.recall.side_effect = RuntimeError("db gone")
        tools = _register_tools(svc)

        result = asyncio.run(tools["recall"](ids=[1]))

        assert isinstance(result, list)
        assert "Internal error" in result[0]["error"]


# ---------------------------------------------------------------------------
# modify() tool tests
# ---------------------------------------------------------------------------

class TestModifyTool:
    """Test modify tool validates and delegates to svc.memory_store.modify()."""

    def test_modify_update(self):
        svc = _make_svc()
        svc.memory_store.modify.return_value = {"id": 1, "status": "updated"}
        tools = _register_tools(svc)

        result = asyncio.run(tools["modify"](
            id=1, action="update", content="new content",
        ))

        assert result == {"id": 1, "status": "updated"}
        call_kwargs = svc.memory_store.modify.call_args.kwargs
        assert call_kwargs["memory_id"] == 1
        assert call_kwargs["action"] == "update"
        assert call_kwargs["content"] == "new content"

    def test_modify_inactivate(self):
        svc = _make_svc()
        svc.memory_store.modify.return_value = {"id": 1, "status": "inactivated"}
        tools = _register_tools(svc)

        result = asyncio.run(tools["modify"](
            id=1, action="inactivate", reason="outdated",
        ))

        assert result["status"] == "inactivated"

    def test_modify_invalid_action(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["modify"](id=1, action="destroy"))

        assert "error" in result
        assert "invalid action" in result["error"]

    def test_modify_invalid_memory_type(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["modify"](
            id=1, action="update", memory_type="banana",
        ))

        assert "error" in result
        assert "memory_type" in result["error"]

    def test_modify_invalid_importance(self):
        svc = _make_svc()
        tools = _register_tools(svc)

        result = asyncio.run(tools["modify"](
            id=1, action="update", importance=2.0,
        ))

        assert "error" in result
        assert "importance" in result["error"]
