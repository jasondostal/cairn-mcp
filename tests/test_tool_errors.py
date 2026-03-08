"""Tests for MCP tool error propagation.

Verifies that when service methods raise exceptions, tools catch them
and return structured {"error": "..."} dicts rather than letting
exceptions propagate to the MCP transport.
"""

import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from cairn.core.utils import ValidationError
from cairn.tools.memory import register as register_memory
from cairn.tools.work_items import register as register_work_items
from cairn.tools.deliverables import register as register_deliverables


# ---------------------------------------------------------------------------
# Test infrastructure (shared with test_tool_memory.py pattern)
# ---------------------------------------------------------------------------

class MockMCP:
    def __init__(self):
        self.tools: dict[str, callable] = {}

    def tool(self, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


@dataclass
class MockBudgetConfig:
    search: int = 0
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
    svc = MagicMock()
    svc.config = MockConfig()
    svc.event_bus = None
    svc.db = MagicMock()
    for key, val in overrides.items():
        setattr(svc, key, val)
    return svc


# ---------------------------------------------------------------------------
# Memory tool error propagation
# ---------------------------------------------------------------------------

class TestMemoryToolErrors:
    """Memory tools should catch exceptions and return error dicts."""

    def _get_tools(self, svc):
        mcp = MockMCP()
        register_memory(mcp, svc)
        return mcp.tools

    def test_store_valueerror_returns_error_dict(self):
        """ValidationError from validate_store → {"error": "..."}."""
        svc = _make_svc()
        tools = self._get_tools(svc)

        # Empty content triggers ValidationError in validate_store
        result = asyncio.run(tools["store"](content="  ", project="cairn"))

        assert isinstance(result, dict)
        assert "error" in result
        # Should NOT say "Internal error" — it's a validation error
        assert "Internal error" not in result["error"]

    def test_store_generic_exception_returns_internal_error(self):
        """Generic Exception from service → {"error": "Internal error: ..."}."""
        svc = _make_svc()
        svc.memory_store.store.side_effect = ConnectionError("pg gone")
        tools = self._get_tools(svc)

        result = asyncio.run(tools["store"](content="valid", project="cairn"))

        assert isinstance(result, dict)
        assert "Internal error" in result["error"]
        assert "pg gone" in result["error"]

    def test_search_valueerror_returns_error_list(self):
        """ValidationError from validate_search → [{"error": "..."}]."""
        svc = _make_svc()
        tools = self._get_tools(svc)

        result = asyncio.run(tools["search"](query=""))

        assert isinstance(result, list)
        assert "error" in result[0]
        assert "Internal error" not in result[0]["error"]

    def test_search_generic_exception_returns_internal_error(self):
        svc = _make_svc()
        svc.search_engine.search.side_effect = OSError("disk full")
        tools = self._get_tools(svc)

        result = asyncio.run(tools["search"](query="test"))

        assert isinstance(result, list)
        assert "Internal error" in result[0]["error"]

    def test_recall_generic_exception_returns_internal_error(self):
        svc = _make_svc()
        svc.memory_store.recall.side_effect = TimeoutError("slow db")
        tools = self._get_tools(svc)

        result = asyncio.run(tools["recall"](ids=[1]))

        assert isinstance(result, list)
        assert "Internal error" in result[0]["error"]

    def test_modify_generic_exception_returns_internal_error(self):
        svc = _make_svc()
        svc.memory_store.modify.side_effect = RuntimeError("modify boom")
        tools = self._get_tools(svc)

        result = asyncio.run(tools["modify"](id=1, action="update"))

        assert isinstance(result, dict)
        assert "Internal error" in result["error"]

    def test_ingest_missing_content_and_url(self):
        """ingest() with no content, url, or file_path → error."""
        svc = _make_svc()
        tools = self._get_tools(svc)

        result = asyncio.run(tools["ingest"](project="cairn"))

        assert "error" in result
        assert "content" in result["error"].lower() or "url" in result["error"].lower()

    def test_ingest_missing_project(self):
        svc = _make_svc()
        tools = self._get_tools(svc)

        result = asyncio.run(tools["ingest"](content="stuff"))

        assert "error" in result
        assert "project" in result["error"].lower()

    def test_ingest_bad_hint(self):
        svc = _make_svc()
        tools = self._get_tools(svc)

        result = asyncio.run(tools["ingest"](
            content="stuff", project="cairn", hint="magic",
        ))

        assert "error" in result
        assert "hint" in result["error"]

    def test_ingest_valueerror_returns_error(self):
        svc = _make_svc()
        svc.ingest_pipeline.ingest.side_effect = ValueError("bad content")
        tools = self._get_tools(svc)

        result = asyncio.run(tools["ingest"](content="stuff", project="cairn"))

        assert "error" in result
        assert "bad content" in result["error"]
        assert "Internal error" not in result["error"]

    def test_ingest_generic_exception_returns_internal_error(self):
        svc = _make_svc()
        svc.ingest_pipeline.ingest.side_effect = RuntimeError("boom")
        tools = self._get_tools(svc)

        result = asyncio.run(tools["ingest"](content="stuff", project="cairn"))

        assert "error" in result
        assert "Internal error" in result["error"]

    def test_consolidate_empty_project(self):
        svc = _make_svc()
        tools = self._get_tools(svc)

        result = asyncio.run(tools["consolidate"](project=""))

        assert "error" in result
        assert "project" in result["error"].lower()

    def test_consolidate_engine_unavailable(self):
        svc = _make_svc()
        svc.consolidation_engine = None
        tools = self._get_tools(svc)

        result = asyncio.run(tools["consolidate"](project="cairn"))

        assert "error" in result
        assert "not available" in result["error"]


# ---------------------------------------------------------------------------
# Work items tool error propagation
# ---------------------------------------------------------------------------

class TestWorkItemsToolErrors:
    """work_items() should catch exceptions and return error dicts."""

    def _get_tools(self, svc):
        mcp = MockMCP()
        register_work_items(mcp, svc)
        return mcp.tools

    def test_valueerror_returns_error(self):
        svc = _make_svc()
        svc.work_item_manager.create.side_effect = ValueError("invalid priority")
        tools = self._get_tools(svc)

        result = asyncio.run(tools["work_items"](
            action="create", project="cairn", title="test",
        ))

        assert "error" in result
        assert "invalid priority" in result["error"]
        assert "Internal error" not in result["error"]

    def test_generic_exception_returns_internal_error(self):
        svc = _make_svc()
        svc.work_item_manager.create.side_effect = RuntimeError("db crash")
        tools = self._get_tools(svc)

        result = asyncio.run(tools["work_items"](
            action="create", project="cairn", title="test",
        ))

        assert "error" in result
        assert "Internal error" in result["error"]

    def test_unknown_action_returns_error(self):
        svc = _make_svc()
        tools = self._get_tools(svc)

        result = asyncio.run(tools["work_items"](action="explode"))

        assert "error" in result
        assert "Unknown action" in result["error"]


# ---------------------------------------------------------------------------
# Deliverables tool error propagation
# ---------------------------------------------------------------------------

class TestDeliverablesToolErrors:
    """deliverables() should catch exceptions and return error dicts."""

    def _get_tools(self, svc):
        mcp = MockMCP()
        register_deliverables(mcp, svc)
        return mcp.tools

    def test_valueerror_returns_error(self):
        svc = _make_svc()
        svc.deliverable_manager.create.side_effect = ValueError("bad input")
        tools = self._get_tools(svc)

        result = asyncio.run(tools["deliverables"](
            action="create", work_item_id=1, description="test",
        ))

        assert "error" in result
        assert "bad input" in result["error"]
        assert "Internal error" not in result["error"]

    def test_generic_exception_returns_internal_error(self):
        svc = _make_svc()
        svc.deliverable_manager.create.side_effect = RuntimeError("boom")
        tools = self._get_tools(svc)

        result = asyncio.run(tools["deliverables"](
            action="create", work_item_id=1, description="test",
        ))

        assert "error" in result
        assert "Internal error" in result["error"]

    def test_unknown_action_returns_error(self):
        svc = _make_svc()
        tools = self._get_tools(svc)

        result = asyncio.run(tools["deliverables"](action="nuke"))

        assert "error" in result
        assert "Unknown action" in result["error"]
