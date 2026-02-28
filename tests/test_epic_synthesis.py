"""Tests for epic result synthesis — deliverable aggregation (ca-153)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from cairn.core.deliverables import DeliverableManager


class TestCollectChildDeliverables:
    """Test DeliverableManager.collect_child_deliverables()."""

    def _make_dm(self):
        db = MagicMock()
        dm = DeliverableManager(db)
        return dm, db

    def test_collects_from_children(self):
        dm, db = self._make_dm()

        db.execute.return_value = [
            {
                "id": 1, "work_item_id": 11, "version": 1, "status": "approved",
                "summary": "Implemented JWT auth",
                "changes": json.dumps([{"description": "Added jwt.py"}]),
                "decisions": json.dumps([{"decision": "Use RS256"}]),
                "open_items": json.dumps([]),
                "metrics": json.dumps({"total_activities": 5}),
                "reviewer_notes": None, "reviewed_by": None, "reviewed_at": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "work_item_title": "Implement JWT", "work_item_status": "done",
                "seq_num": 11, "work_item_prefix": "ca",
            },
            {
                "id": 2, "work_item_id": 12, "version": 2, "status": "approved",
                "summary": "Built login UI",
                "changes": json.dumps([{"description": "Added LoginForm.tsx"}]),
                "decisions": json.dumps([]),
                "open_items": json.dumps([{"description": "Add 2FA"}]),
                "metrics": json.dumps({"total_activities": 3}),
                "reviewer_notes": None, "reviewed_by": None, "reviewed_at": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "work_item_title": "Build login UI", "work_item_status": "done",
                "seq_num": 12, "work_item_prefix": "ca",
            },
        ]

        result = dm.collect_child_deliverables(10)

        assert len(result) == 2
        assert result[0]["work_item_title"] == "Implement JWT"
        assert result[0]["display_id"] == "ca-11"
        assert result[1]["work_item_title"] == "Build login UI"
        assert result[1]["display_id"] == "ca-12"

    def test_empty_when_no_children(self):
        dm, db = self._make_dm()
        db.execute.return_value = []

        result = dm.collect_child_deliverables(10)
        assert result == []


class TestSynthesizeEpic:
    """Test DeliverableManager.synthesize_epic()."""

    def _make_dm(self):
        db = MagicMock()
        dm = DeliverableManager(db)
        return dm, db

    def _child_row(self, id, wi_id, title, summary, changes=None, decisions=None,
                   open_items=None, metrics=None, status="approved", wi_status="done"):
        return {
            "id": id, "work_item_id": wi_id, "version": 1, "status": status,
            "summary": summary,
            "changes": json.dumps(changes or []),
            "decisions": json.dumps(decisions or []),
            "open_items": json.dumps(open_items or []),
            "metrics": json.dumps(metrics or {}),
            "reviewer_notes": None, "reviewed_by": None, "reviewed_at": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "work_item_title": title, "work_item_status": wi_status,
            "seq_num": wi_id, "work_item_prefix": "ca",
        }

    def test_aggregates_changes(self):
        dm, db = self._make_dm()

        db.execute.return_value = [
            self._child_row(1, 11, "Task A", "Did A",
                           changes=[{"description": "Changed file_a.py", "type": "code"}]),
            self._child_row(2, 12, "Task B", "Did B",
                           changes=[{"description": "Changed file_b.py", "type": "code"},
                                    {"description": "Updated config", "type": "config"}]),
        ]

        db.execute_one.side_effect = [
            {"next_ver": 1},
            {"id": 100, "version": 1, "status": "draft",
             "created_at": datetime.now(timezone.utc)},
        ]

        result = dm.synthesize_epic(10)
        assert result["id"] == 100

        insert_call = db.execute_one.call_args_list[1]
        params = insert_call[0][1]
        changes = json.loads(params[4])
        assert len(changes) == 3
        assert all("source" in c for c in changes)

    def test_aggregates_decisions(self):
        dm, db = self._make_dm()

        db.execute.return_value = [
            self._child_row(1, 11, "Task A", "Did A",
                           decisions=[{"decision": "Use JWT", "rationale": "Standard"}]),
            self._child_row(2, 12, "Task B", "Did B",
                           decisions=[{"decision": "Use bcrypt", "rationale": "Secure"}]),
        ]

        db.execute_one.side_effect = [
            {"next_ver": 1},
            {"id": 100, "version": 1, "status": "draft",
             "created_at": datetime.now(timezone.utc)},
        ]

        dm.synthesize_epic(10)

        insert_call = db.execute_one.call_args_list[1]
        params = insert_call[0][1]
        decisions = json.loads(params[5])
        assert len(decisions) == 2
        assert decisions[0]["source"] == "ca-11: Task A"

    def test_aggregates_metrics(self):
        dm, db = self._make_dm()

        db.execute.return_value = [
            self._child_row(1, 11, "Task A", "A",
                           metrics={"total_activities": 5, "heartbeat_count": 3}),
            self._child_row(2, 12, "Task B", "B",
                           metrics={"total_activities": 8, "heartbeat_count": 4}),
        ]

        db.execute_one.side_effect = [
            {"next_ver": 1},
            {"id": 100, "version": 1, "status": "draft",
             "created_at": datetime.now(timezone.utc)},
        ]

        dm.synthesize_epic(10)

        insert_call = db.execute_one.call_args_list[1]
        params = insert_call[0][1]
        metrics = json.loads(params[7])
        assert metrics["total_activities"] == 13
        assert metrics["heartbeat_count"] == 7
        assert metrics["child_deliverables"] == 2
        assert metrics["approved_count"] == 2

    def test_summary_override(self):
        dm, db = self._make_dm()

        db.execute.return_value = [self._child_row(1, 11, "Task A", "A")]
        db.execute_one.side_effect = [
            {"next_ver": 1},
            {"id": 100, "version": 1, "status": "draft",
             "created_at": datetime.now(timezone.utc)},
        ]

        dm.synthesize_epic(10, summary_override="Custom epic summary")

        insert_call = db.execute_one.call_args_list[1]
        params = insert_call[0][1]
        assert params[3] == "Custom epic summary"

    def test_auto_generates_summary(self):
        dm, db = self._make_dm()

        db.execute.return_value = [
            self._child_row(1, 11, "Task A", "Summary for A"),
            self._child_row(2, 12, "Task B", "Summary for B"),
        ]
        db.execute_one.side_effect = [
            {"next_ver": 1},
            {"id": 100, "version": 1, "status": "draft",
             "created_at": datetime.now(timezone.utc)},
        ]

        dm.synthesize_epic(10)

        insert_call = db.execute_one.call_args_list[1]
        params = insert_call[0][1]
        summary = params[3]
        assert "2 subtask deliverable(s)" in summary
        assert "ca-11" in summary
        assert "Summary for A" in summary

    def test_raises_on_no_children(self):
        dm, db = self._make_dm()
        db.execute.return_value = []

        with pytest.raises(ValueError, match="No child deliverables"):
            dm.synthesize_epic(10)

    def test_open_items_tagged_with_source(self):
        dm, db = self._make_dm()

        db.execute.return_value = [
            self._child_row(1, 11, "Task A", "A",
                           open_items=[{"description": "Add 2FA", "priority": "high"}]),
            self._child_row(2, 12, "Task B", "B",
                           open_items=[{"description": "Rate limit", "priority": "medium"}]),
        ]
        db.execute_one.side_effect = [
            {"next_ver": 1},
            {"id": 100, "version": 1, "status": "draft",
             "created_at": datetime.now(timezone.utc)},
        ]

        dm.synthesize_epic(10)

        insert_call = db.execute_one.call_args_list[1]
        params = insert_call[0][1]
        open_items = json.loads(params[6])
        assert len(open_items) == 2
        assert open_items[0]["source"] == "ca-11: Task A"
        assert open_items[0]["description"] == "Add 2FA"

    def test_creates_draft_status(self):
        dm, db = self._make_dm()

        db.execute.return_value = [self._child_row(1, 11, "Task A", "A")]
        db.execute_one.side_effect = [
            {"next_ver": 1},
            {"id": 100, "version": 1, "status": "draft",
             "created_at": datetime.now(timezone.utc)},
        ]

        result = dm.synthesize_epic(10)
        assert result["status"] == "draft"
