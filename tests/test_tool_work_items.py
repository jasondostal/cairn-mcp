"""Tests for MCP work_items tool CRUD operations.

Tests the work_items() tool registered inside cairn.tools.work_items.register()
with mocked svc.work_item_manager.
"""

import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from cairn.tools.work_items import register


# ---------------------------------------------------------------------------
# Test infrastructure
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


def _get_tool(svc):
    mcp = MockMCP()
    register(mcp, svc)
    return mcp.tools["work_items"]


# ---------------------------------------------------------------------------
# create action
# ---------------------------------------------------------------------------

class TestWorkItemsCreate:
    def test_create_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.create.return_value = {"id": 1, "title": "Fix bug"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="create", project="cairn", title="Fix bug"))

        assert result == {"id": 1, "title": "Fix bug"}
        svc.work_item_manager.create.assert_called_once()
        kwargs = svc.work_item_manager.create.call_args.kwargs
        assert kwargs["project"] == "cairn"
        assert kwargs["title"] == "Fix bug"

    def test_create_with_optional_fields(self):
        svc = _make_svc()
        svc.work_item_manager.create.return_value = {"id": 2}
        tool = _get_tool(svc)

        asyncio.run(tool(
            action="create", project="cairn", title="Epic",
            description="A big thing", item_type="epic", priority=2,
            risk_tier=1, constraints={"max_hours": 8},
        ))

        kwargs = svc.work_item_manager.create.call_args.kwargs
        assert kwargs["description"] == "A big thing"
        assert kwargs["item_type"] == "epic"
        assert kwargs["priority"] == 2
        assert kwargs["risk_tier"] == 1
        assert kwargs["constraints"] == {"max_hours": 8}

    def test_create_missing_project(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="create", title="Fix bug"))

        assert "error" in result
        assert "project" in result["error"].lower()
        svc.work_item_manager.create.assert_not_called()

    def test_create_missing_title(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="create", project="cairn"))

        assert "error" in result
        assert "title" in result["error"].lower()


# ---------------------------------------------------------------------------
# list action
# ---------------------------------------------------------------------------

class TestWorkItemsList:
    def test_list_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.list_items.return_value = [
            {"id": 1, "title": "Task A"},
            {"id": 2, "title": "Task B"},
        ]
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="list", project="cairn", status="open"))

        assert len(result) == 2
        kwargs = svc.work_item_manager.list_items.call_args.kwargs
        assert kwargs["project"] == "cairn"
        assert kwargs["status"] == "open"

    def test_list_with_pagination(self):
        svc = _make_svc()
        svc.work_item_manager.list_items.return_value = []
        tool = _get_tool(svc)

        asyncio.run(tool(action="list", limit=5, offset=10))

        kwargs = svc.work_item_manager.list_items.call_args.kwargs
        assert kwargs["limit"] == 5
        assert kwargs["offset"] == 10

    def test_list_caps_limit_at_max(self):
        """limit is capped at MAX_LIMIT (100)."""
        svc = _make_svc()
        svc.work_item_manager.list_items.return_value = []
        tool = _get_tool(svc)

        asyncio.run(tool(action="list", limit=500))

        kwargs = svc.work_item_manager.list_items.call_args.kwargs
        assert kwargs["limit"] == 100  # MAX_LIMIT


# ---------------------------------------------------------------------------
# update action
# ---------------------------------------------------------------------------

class TestWorkItemsUpdate:
    def test_update_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.update.return_value = {"id": 1, "status": "in_progress"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="update", work_item_id=1, status="in_progress",
        ))

        assert result == {"id": 1, "status": "in_progress"}
        svc.work_item_manager.update.assert_called_once()
        # First arg is work_item_id
        args = svc.work_item_manager.update.call_args
        assert args[0][0] == 1
        assert args[1]["status"] == "in_progress"

    def test_update_multiple_fields(self):
        svc = _make_svc()
        svc.work_item_manager.update.return_value = {"id": 1}
        tool = _get_tool(svc)

        asyncio.run(tool(
            action="update", work_item_id=1,
            title="New title", description="New desc", priority=3,
        ))

        kwargs = svc.work_item_manager.update.call_args.kwargs
        assert kwargs["title"] == "New title"
        assert kwargs["description"] == "New desc"
        assert kwargs["priority"] == 3

    def test_update_missing_work_item_id(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="update", title="New"))

        assert "error" in result
        assert "work_item_id" in result["error"]


# ---------------------------------------------------------------------------
# complete action
# ---------------------------------------------------------------------------

class TestWorkItemsComplete:
    def test_complete_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.complete.return_value = {"id": 1, "status": "done"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="complete", work_item_id=1))

        assert result["status"] == "done"
        svc.work_item_manager.complete.assert_called_once_with(
            1, session_name=None,
        )

    def test_complete_missing_work_item_id(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="complete"))

        assert "error" in result
        assert "work_item_id" in result["error"]

    @patch("cairn.tools.work_items.lock_manager")
    def test_complete_releases_locks(self, mock_lock_manager):
        """complete with project set should auto-release locks."""
        svc = _make_svc()
        svc.work_item_manager.complete.return_value = {"id": 1, "status": "done"}
        mock_lock_manager.release.return_value = ["file.py"]
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="complete", work_item_id=1, project="cairn",
        ))

        assert result["locks_released"] == ["file.py"]
        mock_lock_manager.release.assert_called_once_with(
            "cairn", work_item_id="1",
        )


# ---------------------------------------------------------------------------
# get action
# ---------------------------------------------------------------------------

class TestWorkItemsGet:
    def test_get_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.get.return_value = {"id": 5, "title": "Task"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="get", work_item_id=5))

        assert result["id"] == 5
        svc.work_item_manager.get.assert_called_once_with(5)

    def test_get_missing_id(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="get"))

        assert "error" in result


# ---------------------------------------------------------------------------
# claim action
# ---------------------------------------------------------------------------

class TestWorkItemsClaim:
    def test_claim_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.claim.return_value = {"id": 1, "assignee": "agent-1"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="claim", work_item_id=1, assignee="agent-1",
        ))

        assert result["assignee"] == "agent-1"
        svc.work_item_manager.claim.assert_called_once_with(
            1, "agent-1", session_name=None,
        )

    def test_claim_missing_assignee(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="claim", work_item_id=1))

        assert "error" in result
        assert "assignee" in result["error"]


# ---------------------------------------------------------------------------
# block / unblock actions
# ---------------------------------------------------------------------------

class TestWorkItemsDependencies:
    def test_block_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.block.return_value = {"status": "blocked"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="block", blocker_id=1, blocked_id=2,
        ))

        svc.work_item_manager.block.assert_called_once_with(1, 2)

    def test_block_missing_ids(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="block", blocker_id=1))

        assert "error" in result

    def test_unblock_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.unblock.return_value = {"status": "unblocked"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="unblock", blocker_id=1, blocked_id=2,
        ))

        svc.work_item_manager.unblock.assert_called_once_with(1, 2)


# ---------------------------------------------------------------------------
# ready action
# ---------------------------------------------------------------------------

class TestWorkItemsReady:
    def test_ready_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.ready_queue.return_value = [{"id": 3}]
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="ready", project="cairn"))

        svc.work_item_manager.ready_queue.assert_called_once()
        assert result == [{"id": 3}]

    def test_ready_missing_project(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="ready"))

        assert "error" in result
        assert "project" in result["error"]


# ---------------------------------------------------------------------------
# link_memories action
# ---------------------------------------------------------------------------

class TestWorkItemsLinkMemories:
    def test_link_memories_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.link_memories.return_value = {"linked": 2}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="link_memories", work_item_id=1, memory_ids=[10, 20],
        ))

        svc.work_item_manager.link_memories.assert_called_once_with(1, [10, 20])

    def test_link_memories_missing_params(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="link_memories", work_item_id=1))

        assert "error" in result


# ---------------------------------------------------------------------------
# heartbeat action
# ---------------------------------------------------------------------------

class TestWorkItemsHeartbeat:
    def test_heartbeat_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.heartbeat.return_value = {"ok": True}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="heartbeat", work_item_id=1, assignee="agent-1",
            note="making progress",
        ))

        kwargs = svc.work_item_manager.heartbeat.call_args.kwargs
        assert kwargs["note"] == "making progress"

    def test_heartbeat_missing_assignee(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="heartbeat", work_item_id=1))

        assert "error" in result


# ---------------------------------------------------------------------------
# gate actions
# ---------------------------------------------------------------------------

class TestWorkItemsGates:
    def test_set_gate_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.set_gate.return_value = {"gated": True}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="set_gate", work_item_id=1, gate_type="human",
        ))

        svc.work_item_manager.set_gate.assert_called_once()

    def test_set_gate_missing_type(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="set_gate", work_item_id=1))

        assert "error" in result

    def test_resolve_gate_calls_manager(self):
        svc = _make_svc()
        svc.work_item_manager.resolve_gate.return_value = {"resolved": True}
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="resolve_gate", work_item_id=1))

        svc.work_item_manager.resolve_gate.assert_called_once()

    def test_resolve_gate_missing_id(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="resolve_gate"))

        assert "error" in result
