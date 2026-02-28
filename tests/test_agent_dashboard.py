"""Tests for concurrent agent observability — dashboard (ca-159)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from cairn.core.agent_dashboard import AgentDashboard
from cairn.core.resource_lock import ResourceLockManager


def _make_dashboard(lock_manager=None):
    db = MagicMock()
    dashboard = AgentDashboard(db, lock_manager=lock_manager)
    return dashboard, db


class TestActiveAgents:
    """Test active agent listing."""

    def test_no_active_agents(self):
        dash, db = _make_dashboard()
        db.execute.return_value = []
        result = dash.active_agents()
        assert result == []

    def test_single_agent_single_item(self):
        dash, db = _make_dashboard()
        db.execute.return_value = [
            {
                "assignee": "agent-1",
                "id": 1, "seq_num": 42, "title": "Fix bug",
                "agent_state": "working", "last_heartbeat": datetime.now(timezone.utc),
                "heartbeat_age_minutes": 2.5,
                "project": "cairn", "work_item_prefix": "ca",
            },
        ]
        result = dash.active_agents()
        assert len(result) == 1
        assert result[0]["agent_name"] == "agent-1"
        assert result[0]["total_items"] == 1
        assert result[0]["work_items"][0]["display_id"] == "ca-42"
        assert result[0]["work_items"][0]["stale"] is False

    def test_stale_agent_detection(self):
        dash, db = _make_dashboard()
        db.execute.return_value = [
            {
                "assignee": "agent-1",
                "id": 1, "seq_num": 42, "title": "Stuck task",
                "agent_state": "working", "last_heartbeat": datetime.now(timezone.utc),
                "heartbeat_age_minutes": 15.0,
                "project": "cairn", "work_item_prefix": "ca",
            },
        ]
        result = dash.active_agents()
        assert result[0]["work_items"][0]["stale"] is True

    def test_multiple_agents(self):
        dash, db = _make_dashboard()
        db.execute.return_value = [
            {
                "assignee": "agent-1",
                "id": 1, "seq_num": 42, "title": "Task A",
                "agent_state": "working", "last_heartbeat": datetime.now(timezone.utc),
                "heartbeat_age_minutes": 1.0,
                "project": "cairn", "work_item_prefix": "ca",
            },
            {
                "assignee": "agent-2",
                "id": 2, "seq_num": 43, "title": "Task B",
                "agent_state": "working", "last_heartbeat": datetime.now(timezone.utc),
                "heartbeat_age_minutes": 3.0,
                "project": "cairn", "work_item_prefix": "ca",
            },
        ]
        result = dash.active_agents()
        assert len(result) == 2
        names = {a["agent_name"] for a in result}
        assert names == {"agent-1", "agent-2"}

    def test_agent_with_multiple_items(self):
        dash, db = _make_dashboard()
        db.execute.return_value = [
            {
                "assignee": "agent-1",
                "id": 1, "seq_num": 42, "title": "Task A",
                "agent_state": "working", "last_heartbeat": datetime.now(timezone.utc),
                "heartbeat_age_minutes": 1.0,
                "project": "cairn", "work_item_prefix": "ca",
            },
            {
                "assignee": "agent-1",
                "id": 2, "seq_num": 43, "title": "Task B",
                "agent_state": "working", "last_heartbeat": datetime.now(timezone.utc),
                "heartbeat_age_minutes": 2.0,
                "project": "cairn", "work_item_prefix": "ca",
            },
        ]
        result = dash.active_agents()
        assert len(result) == 1
        assert result[0]["total_items"] == 2

    def test_no_heartbeat_not_stale(self):
        dash, db = _make_dashboard()
        db.execute.return_value = [
            {
                "assignee": "agent-1",
                "id": 1, "seq_num": 42, "title": "New task",
                "agent_state": None, "last_heartbeat": None,
                "heartbeat_age_minutes": None,
                "project": "cairn", "work_item_prefix": "ca",
            },
        ]
        result = dash.active_agents()
        assert result[0]["work_items"][0]["stale"] is False


class TestOverview:
    """Test dashboard overview."""

    def test_empty_overview(self):
        dash, db = _make_dashboard()
        db.execute.return_value = []
        result = dash.overview()
        assert result["total_active_agents"] == 0
        assert result["total_active_items"] == 0
        assert result["health"] == "healthy"

    def test_overview_with_agents(self):
        dash, db = _make_dashboard()
        db.execute.return_value = [
            {
                "assignee": "agent-1",
                "id": 1, "seq_num": 42, "title": "Task A",
                "agent_state": "working", "last_heartbeat": datetime.now(timezone.utc),
                "heartbeat_age_minutes": 2.0,
                "project": "cairn", "work_item_prefix": "ca",
            },
            {
                "assignee": "agent-2",
                "id": 2, "seq_num": 43, "title": "Task B",
                "agent_state": "working", "last_heartbeat": datetime.now(timezone.utc),
                "heartbeat_age_minutes": 1.0,
                "project": "cairn", "work_item_prefix": "ca",
            },
        ]
        result = dash.overview()
        assert result["total_active_agents"] == 2
        assert result["total_active_items"] == 2
        assert result["health"] == "healthy"

    def test_overview_degraded_with_stale(self):
        dash, db = _make_dashboard()
        db.execute.return_value = [
            {
                "assignee": "agent-1",
                "id": 1, "seq_num": 42, "title": "Stale task",
                "agent_state": "working", "last_heartbeat": datetime.now(timezone.utc),
                "heartbeat_age_minutes": 20.0,
                "project": "cairn", "work_item_prefix": "ca",
            },
        ]
        result = dash.overview()
        assert result["health"] == "degraded"
        assert result["stale_agents"] == 1

    def test_overview_includes_locks(self):
        lock_mgr = ResourceLockManager()
        lock_mgr.acquire("cairn", ["src/api.py"], "agent-1", "ca-42")
        dash, db = _make_dashboard(lock_manager=lock_mgr)
        db.execute.return_value = [
            {
                "assignee": "agent-1",
                "id": 1, "seq_num": 42, "title": "Task A",
                "agent_state": "working", "last_heartbeat": datetime.now(timezone.utc),
                "heartbeat_age_minutes": 1.0,
                "project": "cairn", "work_item_prefix": "ca",
            },
        ]
        result = dash.overview()
        assert result["locks"]["cairn"] == 1


class TestAgentDetail:
    """Test single agent detail view."""

    def test_agent_detail_active_and_history(self):
        dash, db = _make_dashboard()
        # First call returns active items, second returns completed history
        db.execute.side_effect = [
            [
                {
                    "id": 1, "seq_num": 42, "title": "Current task",
                    "status": "in_progress", "agent_state": "working",
                    "last_heartbeat": datetime.now(timezone.utc),
                    "item_type": "task", "risk_tier": 1,
                    "gate_type": None, "gate_data": None,
                    "heartbeat_age_minutes": 3.0,
                    "project": "cairn", "work_item_prefix": "ca",
                },
            ],
            [
                {
                    "id": 10, "seq_num": 30, "title": "Old task",
                    "completed_at": datetime.now(timezone.utc),
                    "project": "cairn", "work_item_prefix": "ca",
                },
            ],
        ]

        result = dash.agent_detail("agent-1")
        assert result["agent_name"] == "agent-1"
        assert result["total_active"] == 1
        assert result["total_completed"] == 1
        assert result["active_items"][0]["display_id"] == "ca-42"
        assert result["completed_items"][0]["display_id"] == "ca-30"

    def test_agent_detail_empty(self):
        dash, db = _make_dashboard()
        db.execute.side_effect = [[], []]
        result = dash.agent_detail("ghost-agent")
        assert result["total_active"] == 0
        assert result["total_completed"] == 0

    def test_agent_detail_gated_item(self):
        dash, db = _make_dashboard()
        db.execute.side_effect = [
            [
                {
                    "id": 1, "seq_num": 42, "title": "Blocked task",
                    "status": "blocked", "agent_state": "stuck",
                    "last_heartbeat": datetime.now(timezone.utc),
                    "item_type": "task", "risk_tier": 2,
                    "gate_type": "human", "gate_data": {"question": "need approval"},
                    "heartbeat_age_minutes": 5.0,
                    "project": "cairn", "work_item_prefix": "ca",
                },
            ],
            [],
        ]

        result = dash.agent_detail("agent-1")
        item = result["active_items"][0]
        assert item["gated"] is True
        assert item["gate_type"] == "human"
