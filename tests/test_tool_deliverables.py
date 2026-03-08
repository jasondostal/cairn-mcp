"""Tests for MCP deliverables tool.

Tests the deliverables() tool registered inside cairn.tools.deliverables.register()
with mocked svc.deliverable_manager.
"""

import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from cairn.tools.deliverables import register


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
    return mcp.tools["deliverables"]


# ---------------------------------------------------------------------------
# get action
# ---------------------------------------------------------------------------

class TestDeliverablesGet:
    def test_get_returns_deliverable(self):
        svc = _make_svc()
        svc.deliverable_manager.get.return_value = {
            "id": 1, "work_item_id": 10, "summary": "Done",
        }
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="get", work_item_id=10))

        assert result["work_item_id"] == 10
        svc.deliverable_manager.get.assert_called_once_with(10)

    def test_get_not_found(self):
        svc = _make_svc()
        svc.deliverable_manager.get.return_value = None
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="get", work_item_id=99))

        assert "error" in result
        assert "No deliverable" in result["error"]

    def test_get_string_id_converted(self):
        """String work_item_id that is numeric should be converted to int."""
        svc = _make_svc()
        svc.deliverable_manager.get.return_value = {"id": 1}
        tool = _get_tool(svc)

        asyncio.run(tool(action="get", work_item_id="42"))

        svc.deliverable_manager.get.assert_called_once_with(42)

    def test_get_missing_work_item_id(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="get"))

        assert "error" in result
        assert "work_item_id" in result["error"]


# ---------------------------------------------------------------------------
# create action
# ---------------------------------------------------------------------------

class TestDeliverablesCreate:
    def test_create_calls_manager(self):
        svc = _make_svc()
        svc.deliverable_manager.create.return_value = {"id": 1, "status": "draft"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="create", work_item_id=10, description="Summary of work",
        ))

        assert result["status"] == "draft"
        kwargs = svc.deliverable_manager.create.call_args.kwargs
        assert kwargs["work_item_id"] == 10
        assert kwargs["summary"] == "Summary of work"

    def test_create_with_metadata(self):
        svc = _make_svc()
        svc.deliverable_manager.create.return_value = {"id": 1}
        tool = _get_tool(svc)

        meta = {
            "changes": ["Added feature X"],
            "decisions": ["Use PostgreSQL"],
            "open_items": ["Need review"],
            "metrics": {"lines_added": 100},
        }
        asyncio.run(tool(
            action="create", work_item_id=10,
            description="Summary", metadata=meta,
        ))

        kwargs = svc.deliverable_manager.create.call_args.kwargs
        assert kwargs["changes"] == ["Added feature X"]
        assert kwargs["decisions"] == ["Use PostgreSQL"]
        assert kwargs["open_items"] == ["Need review"]
        assert kwargs["metrics"] == {"lines_added": 100}

    def test_create_default_status_draft(self):
        svc = _make_svc()
        svc.deliverable_manager.create.return_value = {"id": 1}
        tool = _get_tool(svc)

        asyncio.run(tool(action="create", work_item_id=10))

        kwargs = svc.deliverable_manager.create.call_args.kwargs
        assert kwargs["status"] == "draft"

    def test_create_missing_work_item_id(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="create", description="stuff"))

        assert "error" in result
        assert "work_item_id" in result["error"]


# ---------------------------------------------------------------------------
# review action
# ---------------------------------------------------------------------------

class TestDeliverablesReview:
    def test_review_approve(self):
        svc = _make_svc()
        svc.deliverable_manager.review.return_value = {"status": "approved"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="review", work_item_id=10, gate_type="approve",
            actor="jdostal", note="Looks good",
        ))

        assert result["status"] == "approved"
        kwargs = svc.deliverable_manager.review.call_args.kwargs
        assert kwargs["work_item_id"] == 10
        assert kwargs["action"] == "approve"
        assert kwargs["reviewer"] == "jdostal"
        assert kwargs["notes"] == "Looks good"

    def test_review_revise(self):
        svc = _make_svc()
        svc.deliverable_manager.review.return_value = {"status": "revised"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="review", work_item_id=10, gate_type="revise",
        ))

        assert result["status"] == "revised"

    def test_review_reject(self):
        svc = _make_svc()
        svc.deliverable_manager.review.return_value = {"status": "rejected"}
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="review", work_item_id=10, gate_type="reject",
        ))

        assert result["status"] == "rejected"

    def test_review_invalid_action(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="review", work_item_id=10, gate_type="nuke",
        ))

        assert "error" in result
        assert "approve" in result["error"]

    def test_review_missing_gate_type(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="review", work_item_id=10))

        assert "error" in result

    def test_review_missing_work_item_id(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="review", gate_type="approve"))

        assert "error" in result


# ---------------------------------------------------------------------------
# submit action
# ---------------------------------------------------------------------------

class TestDeliverablesSubmit:
    def test_submit_calls_manager(self):
        svc = _make_svc()
        svc.deliverable_manager.submit_for_review.return_value = {
            "status": "pending_review",
        }
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="submit", work_item_id=10))

        assert result["status"] == "pending_review"
        svc.deliverable_manager.submit_for_review.assert_called_once_with(10)

    def test_submit_missing_work_item_id(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="submit"))

        assert "error" in result


# ---------------------------------------------------------------------------
# pending action
# ---------------------------------------------------------------------------

class TestDeliverablesPending:
    def test_pending_calls_manager(self):
        svc = _make_svc()
        svc.deliverable_manager.list_pending.return_value = [
            {"id": 1}, {"id": 2},
        ]
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="pending", project="cairn"))

        assert len(result) == 2
        kwargs = svc.deliverable_manager.list_pending.call_args.kwargs
        assert kwargs["project"] == "cairn"

    def test_pending_caps_limit(self):
        svc = _make_svc()
        svc.deliverable_manager.list_pending.return_value = []
        tool = _get_tool(svc)

        asyncio.run(tool(action="pending", limit=500))

        kwargs = svc.deliverable_manager.list_pending.call_args.kwargs
        assert kwargs["limit"] == 100  # MAX_LIMIT


# ---------------------------------------------------------------------------
# synthesize action
# ---------------------------------------------------------------------------

class TestDeliverablesSynthesize:
    def test_synthesize_calls_manager(self):
        svc = _make_svc()
        svc.deliverable_manager.synthesize_epic.return_value = {
            "status": "synthesized",
        }
        tool = _get_tool(svc)

        result = asyncio.run(tool(
            action="synthesize", work_item_id=10,
            description="Override summary",
        ))

        assert result["status"] == "synthesized"
        svc.deliverable_manager.synthesize_epic.assert_called_once_with(
            10, summary_override="Override summary",
        )

    def test_synthesize_missing_work_item_id(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="synthesize"))

        assert "error" in result


# ---------------------------------------------------------------------------
# children action
# ---------------------------------------------------------------------------

class TestDeliverablesChildren:
    def test_children_calls_manager(self):
        svc = _make_svc()
        svc.deliverable_manager.collect_child_deliverables.return_value = [
            {"id": 1}, {"id": 2},
        ]
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="children", work_item_id=10))

        assert result == {"items": [{"id": 1}, {"id": 2}]}

    def test_children_missing_work_item_id(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="children"))

        assert "error" in result


# ---------------------------------------------------------------------------
# unknown action
# ---------------------------------------------------------------------------

class TestDeliverablesUnknownAction:
    def test_unknown_action(self):
        svc = _make_svc()
        tool = _get_tool(svc)

        result = asyncio.run(tool(action="explode"))

        assert "error" in result
        assert "Unknown action" in result["error"]
