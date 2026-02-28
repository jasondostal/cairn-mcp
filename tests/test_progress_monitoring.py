"""Tests for coordinator progress monitoring (ca-152)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


class TestProgressSummary:
    """Test WorkItemManager.progress_summary()."""

    def _make_wim(self):
        from cairn.core.work_items import WorkItemManager
        db = MagicMock()
        event_bus = MagicMock()
        wim = WorkItemManager(db, event_bus)
        return wim, db

    def _make_item(self, id=1, status="open", parent_id=None):
        return {
            "id": id, "seq_num": id, "title": f"Item {id}", "status": status,
            "project_id": 1, "display_id": f"ca-{id}", "project_name": "cairn",
            "parent_id": parent_id, "work_item_prefix": "ca",
        }

    def _make_child_row(self, id, title, status="open", assignee=None,
                        agent_state=None, heartbeat_age=None, gate_type=None):
        return {
            "id": id, "seq_num": id, "title": title, "status": status,
            "assignee": assignee, "agent_state": agent_state,
            "last_heartbeat": datetime.now(timezone.utc) if heartbeat_age is not None else None,
            "gate_type": gate_type, "risk_tier": 1, "item_type": "subtask",
            "work_item_prefix": "ca",
            "heartbeat_age_minutes": heartbeat_age,
        }

    def test_all_complete(self):
        wim, db = self._make_wim()
        parent = self._make_item(id=10)
        wim._resolve_id = lambda wid: parent
        wim._display_id = lambda i: f"ca-{i['id']}"
        wim._display_id_from_row = lambda r: f"ca-{r['seq_num']}"

        db.execute.return_value = [
            self._make_child_row(11, "Task A", status="done", heartbeat_age=5.0),
            self._make_child_row(12, "Task B", status="done", heartbeat_age=3.0),
            self._make_child_row(13, "Task C", status="done", heartbeat_age=1.0),
        ]

        result = wim.progress_summary(10)

        assert result["all_complete"] is True
        assert result["total_children"] == 3
        assert result["status_counts"]["done"] == 3
        assert result["progress_line"] == "3/3 complete"
        assert result["stale_agents"] == []
        assert result["blocked_items"] == []

    def test_mixed_statuses(self):
        wim, db = self._make_wim()
        parent = self._make_item(id=10)
        wim._resolve_id = lambda wid: parent
        wim._display_id = lambda i: f"ca-{i['id']}"
        wim._display_id_from_row = lambda r: f"ca-{r['seq_num']}"

        db.execute.return_value = [
            self._make_child_row(11, "Done task", status="done", heartbeat_age=30.0),
            self._make_child_row(12, "WIP task", status="in_progress", assignee="agent:cc", heartbeat_age=2.0),
            self._make_child_row(13, "Open task", status="open"),
            self._make_child_row(14, "Blocked task", status="blocked", gate_type="human"),
        ]

        result = wim.progress_summary(10)

        assert result["all_complete"] is False
        assert result["total_children"] == 4
        assert result["status_counts"]["done"] == 1
        assert result["status_counts"]["in_progress"] == 1
        assert result["status_counts"]["open"] == 1
        assert result["status_counts"]["blocked"] == 1
        assert "1/4 complete" in result["progress_line"]
        assert "1 in progress" in result["progress_line"]
        assert "1 blocked" in result["progress_line"]

    def test_stale_agent_detection(self):
        wim, db = self._make_wim()
        parent = self._make_item(id=10)
        wim._resolve_id = lambda wid: parent
        wim._display_id = lambda i: f"ca-{i['id']}"
        wim._display_id_from_row = lambda r: f"ca-{r['seq_num']}"

        db.execute.return_value = [
            self._make_child_row(11, "Healthy worker", status="in_progress",
                                 assignee="agent:a", heartbeat_age=3.0, agent_state="working"),
            self._make_child_row(12, "Stale worker", status="in_progress",
                                 assignee="agent:b", heartbeat_age=25.0, agent_state="working"),
            self._make_child_row(13, "Very stale", status="in_progress",
                                 assignee="agent:c", heartbeat_age=60.0, agent_state="working"),
        ]

        result = wim.progress_summary(10, stale_threshold_minutes=10)

        assert len(result["stale_agents"]) == 2
        stale_names = [s["assignee"] for s in result["stale_agents"]]
        assert "agent:b" in stale_names
        assert "agent:c" in stale_names
        assert "agent:a" not in stale_names
        assert "2 stale" in result["progress_line"]

    def test_blocked_items_detected(self):
        wim, db = self._make_wim()
        parent = self._make_item(id=10)
        wim._resolve_id = lambda wid: parent
        wim._display_id = lambda i: f"ca-{i['id']}"
        wim._display_id_from_row = lambda r: f"ca-{r['seq_num']}"

        db.execute.return_value = [
            self._make_child_row(11, "Normal", status="in_progress", heartbeat_age=1.0),
            self._make_child_row(12, "Gated", status="blocked", gate_type="human"),
            self._make_child_row(13, "Also blocked", status="blocked", gate_type="review"),
        ]

        result = wim.progress_summary(10)

        assert len(result["blocked_items"]) == 2
        assert result["blocked_items"][0]["gate_type"] == "human"
        assert result["blocked_items"][1]["gate_type"] == "review"

    def test_no_children(self):
        wim, db = self._make_wim()
        parent = self._make_item(id=10)
        wim._resolve_id = lambda wid: parent
        wim._display_id = lambda i: f"ca-{i['id']}"
        wim._display_id_from_row = lambda r: f"ca-{r['seq_num']}"

        db.execute.return_value = []

        result = wim.progress_summary(10)

        assert result["total_children"] == 0
        assert result["all_complete"] is False
        assert result["progress_line"] == "0/0 complete"

    def test_nonexistent_parent_raises(self):
        wim, db = self._make_wim()
        wim._resolve_id = lambda wid: None

        with pytest.raises(ValueError, match="not found"):
            wim.progress_summary(999)

    def test_custom_stale_threshold(self):
        wim, db = self._make_wim()
        parent = self._make_item(id=10)
        wim._resolve_id = lambda wid: parent
        wim._display_id = lambda i: f"ca-{i['id']}"
        wim._display_id_from_row = lambda r: f"ca-{r['seq_num']}"

        db.execute.return_value = [
            self._make_child_row(11, "Worker", status="in_progress",
                                 assignee="agent:a", heartbeat_age=8.0),
        ]

        # Default threshold (10 min) — not stale
        result = wim.progress_summary(10, stale_threshold_minutes=10)
        assert len(result["stale_agents"]) == 0

        # Stricter threshold (5 min) — now stale
        result = wim.progress_summary(10, stale_threshold_minutes=5)
        assert len(result["stale_agents"]) == 1

    def test_no_heartbeat_not_stale(self):
        """Items without a heartbeat (never started) aren't flagged as stale."""
        wim, db = self._make_wim()
        parent = self._make_item(id=10)
        wim._resolve_id = lambda wid: parent
        wim._display_id = lambda i: f"ca-{i['id']}"
        wim._display_id_from_row = lambda r: f"ca-{r['seq_num']}"

        db.execute.return_value = [
            self._make_child_row(11, "Unclaimed", status="in_progress",
                                 assignee="agent:a", heartbeat_age=None),
        ]

        result = wim.progress_summary(10)
        assert len(result["stale_agents"]) == 0

    def test_children_detail_included(self):
        wim, db = self._make_wim()
        parent = self._make_item(id=10)
        wim._resolve_id = lambda wid: parent
        wim._display_id = lambda i: f"ca-{i['id']}"
        wim._display_id_from_row = lambda r: f"ca-{r['seq_num']}"

        db.execute.return_value = [
            self._make_child_row(11, "Task A", status="done", heartbeat_age=1.0),
            self._make_child_row(12, "Task B", status="in_progress",
                                 assignee="agent:x", heartbeat_age=5.0, agent_state="working"),
        ]

        result = wim.progress_summary(10)

        assert len(result["children"]) == 2
        assert result["children"][0]["display_id"] == "ca-11"
        assert result["children"][0]["status"] == "done"
        assert result["children"][1]["assignee"] == "agent:x"
        assert result["children"][1]["agent_state"] == "working"
        assert result["children"][1]["heartbeat_age_minutes"] == 5.0
