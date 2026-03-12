"""Tests for cairn.core.deliverables.DeliverableManager."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, call

from cairn.core.deliverables import DeliverableManager
from cairn.core.constants import DeliverableStatus


class TestDeliverableManager:
    def _make_manager(self):
        db = MagicMock()
        event_bus = MagicMock()
        mgr = DeliverableManager(db, event_bus=event_bus)
        return mgr, db, event_bus

    def test_create_first_version(self):
        mgr, db, event_bus = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute_one.side_effect = [
            {"next_ver": 1},  # version query
            {"id": 1, "version": 1, "status": "draft", "created_at": now},  # insert
        ]

        result = mgr.create(
            work_item_id=42,
            summary="Implemented the widget",
            changes=[{"type": "file", "path": "widget.py", "action": "created"}],
            decisions=[{"decision": "Used factory pattern", "rationale": "Extensibility"}],
        )

        assert result["id"] == 1
        assert result["version"] == 1
        assert result["status"] == "draft"
        assert result["work_item_id"] == 42

        # Verify insert SQL
        insert_call = db.execute_one.call_args_list[1]
        sql = insert_call[0][0]
        assert "INSERT INTO deliverables" in sql

        # Verify event published
        event_bus.emit.assert_called_once()
        call_kwargs = event_bus.emit.call_args
        assert call_kwargs[0][0] == "deliverable.created"

    def test_create_increments_version(self):
        mgr, db, event_bus = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute_one.side_effect = [
            {"next_ver": 3},  # already has versions 1 and 2
            {"id": 5, "version": 3, "status": "draft", "created_at": now},
        ]

        result = mgr.create(work_item_id=42, summary="Third attempt")

        assert result["version"] == 3
        # Check version passed to insert
        insert_params = db.execute_one.call_args_list[1][0][1]
        assert insert_params[1] == 3  # version param

    def test_get_latest_version(self):
        mgr, db, _ = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute_one.return_value = {
            "id": 1, "work_item_id": 42, "version": 2,
            "status": "pending_review", "summary": "Did the thing",
            "changes": [{"type": "file"}], "decisions": [], "open_items": [],
            "metrics": {}, "reviewer_notes": None, "reviewed_by": None,
            "reviewed_at": None, "created_at": now, "updated_at": now,
        }

        result = mgr.get(42)

        assert result["version"] == 2
        assert result["status"] == "pending_review"
        # Should query without version filter, ORDER BY DESC
        sql = db.execute_one.call_args[0][0]
        assert "ORDER BY version DESC" in sql

    def test_get_specific_version(self):
        mgr, db, _ = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute_one.return_value = {
            "id": 1, "work_item_id": 42, "version": 1,
            "status": "revised", "summary": "First attempt",
            "changes": [], "decisions": [], "open_items": [],
            "metrics": {}, "reviewer_notes": "Needs v2 API",
            "reviewed_by": "jason", "reviewed_at": now,
            "created_at": now, "updated_at": now,
        }

        result = mgr.get(42, version=1)

        assert result["version"] == 1
        sql = db.execute_one.call_args[0][0]
        assert "version = %s" in sql

    def test_get_returns_none_when_missing(self):
        mgr, db, _ = self._make_manager()
        db.execute_one.return_value = None

        result = mgr.get(999)
        assert result is None

    def test_review_approve(self):
        mgr, db, event_bus = self._make_manager()
        now = datetime.now(timezone.utc)
        # Mock get() to return a pending deliverable
        db.execute_one.return_value = {
            "id": 1, "work_item_id": 42, "version": 1,
            "status": "pending_review", "summary": "Did it",
            "changes": [], "decisions": [], "open_items": [],
            "metrics": {}, "reviewer_notes": None, "reviewed_by": None,
            "reviewed_at": None, "created_at": now, "updated_at": now,
        }

        result = mgr.review(42, action="approve", reviewer="jason", notes="LGTM")

        assert result["status"] == DeliverableStatus.APPROVED
        assert result["action"] == "approve"
        assert result["reviewed_by"] == "jason"

        # Verify UPDATE was called
        update_call = db.execute.call_args
        sql = update_call[0][0]
        assert "UPDATE deliverables" in sql

        # Verify event
        event_bus.emit.assert_called()
        call_kwargs = event_bus.emit.call_args
        assert call_kwargs[0][0] == "deliverable.approved"

    def test_review_revise(self):
        mgr, db, event_bus = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute_one.return_value = {
            "id": 1, "work_item_id": 42, "version": 1,
            "status": "draft", "summary": "Attempt",
            "changes": [], "decisions": [], "open_items": [],
            "metrics": {}, "reviewer_notes": None, "reviewed_by": None,
            "reviewed_at": None, "created_at": now, "updated_at": now,
        }

        result = mgr.review(42, action="revise", reviewer="jason", notes="Use v2 API")

        assert result["status"] == DeliverableStatus.REVISED
        assert result["action"] == "revise"

        call_kwargs = event_bus.emit.call_args
        assert call_kwargs[0][0] == "deliverable.revised"

    def test_review_reject(self):
        mgr, db, event_bus = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute_one.return_value = {
            "id": 1, "work_item_id": 42, "version": 1,
            "status": "pending_review", "summary": "Bad approach",
            "changes": [], "decisions": [], "open_items": [],
            "metrics": {}, "reviewer_notes": None, "reviewed_by": None,
            "reviewed_at": None, "created_at": now, "updated_at": now,
        }

        result = mgr.review(42, action="reject", notes="Wrong approach entirely")

        assert result["status"] == DeliverableStatus.REJECTED

    def test_review_invalid_action_raises(self):
        mgr, db, _ = self._make_manager()
        try:
            mgr.review(42, action="yolo")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid review action" in str(e)

    def test_review_already_approved_raises(self):
        mgr, db, _ = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute_one.return_value = {
            "id": 1, "work_item_id": 42, "version": 1,
            "status": "approved", "summary": "Done",
            "changes": [], "decisions": [], "open_items": [],
            "metrics": {}, "reviewer_notes": "LGTM", "reviewed_by": "jason",
            "reviewed_at": now, "created_at": now, "updated_at": now,
        }

        try:
            mgr.review(42, action="reject")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "cannot review" in str(e).lower()

    def test_review_no_deliverable_raises(self):
        mgr, db, _ = self._make_manager()
        db.execute_one.return_value = None

        try:
            mgr.review(999, action="approve")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "No deliverable found" in str(e)

    def test_submit_for_review(self):
        mgr, db, event_bus = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute_one.return_value = {
            "id": 1, "work_item_id": 42, "version": 1,
            "status": "draft", "summary": "Ready",
            "changes": [], "decisions": [], "open_items": [],
            "metrics": {}, "reviewer_notes": None, "reviewed_by": None,
            "reviewed_at": None, "created_at": now, "updated_at": now,
        }

        result = mgr.submit_for_review(42)

        assert result["status"] == DeliverableStatus.PENDING_REVIEW
        event_bus.emit.assert_called_once()

    def test_submit_non_draft_raises(self):
        mgr, db, _ = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute_one.return_value = {
            "id": 1, "work_item_id": 42, "version": 1,
            "status": "approved", "summary": "Done",
            "changes": [], "decisions": [], "open_items": [],
            "metrics": {}, "reviewer_notes": None, "reviewed_by": None,
            "reviewed_at": None, "created_at": now, "updated_at": now,
        }

        try:
            mgr.submit_for_review(42)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "not 'draft'" in str(e)

    def test_list_pending(self):
        mgr, db, _ = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute.return_value = [
            {
                "id": 1, "work_item_id": 42, "version": 1,
                "status": "pending_review", "summary": "Review me",
                "changes": [], "decisions": [], "open_items": [],
                "metrics": {}, "reviewer_notes": None, "reviewed_by": None,
                "reviewed_at": None, "created_at": now, "updated_at": now,
                "work_item_title": "Fix the bug", "project_name": "cairn",
            },
        ]

        result = mgr.list_pending()

        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "pending_review"
        sql = db.execute.call_args[0][0]
        assert "pending_review" in sql

    def test_list_pending_with_project_filter(self):
        mgr, db, _ = self._make_manager()
        db.execute.return_value = []

        result = mgr.list_pending(project="cairn")

        sql = db.execute.call_args[0][0]
        assert "p.name = %s" in sql

    def test_list_for_work_item(self):
        mgr, db, _ = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute.return_value = [
            {
                "id": 2, "work_item_id": 42, "version": 2,
                "status": "draft", "summary": "Second attempt",
                "changes": [], "decisions": [], "open_items": [],
                "metrics": {}, "reviewer_notes": None, "reviewed_by": None,
                "reviewed_at": None, "created_at": now, "updated_at": now,
            },
            {
                "id": 1, "work_item_id": 42, "version": 1,
                "status": "revised", "summary": "First attempt",
                "changes": [], "decisions": [], "open_items": [],
                "metrics": {}, "reviewer_notes": "Use v2", "reviewed_by": "jason",
                "reviewed_at": now, "created_at": now, "updated_at": now,
            },
        ]

        result = mgr.list_for_work_item(42)

        assert len(result) == 2
        assert result[0]["version"] == 2  # newest first

    def test_event_bus_failure_is_silent(self):
        mgr, db, event_bus = self._make_manager()
        now = datetime.now(timezone.utc)
        event_bus.emit.side_effect = Exception("bus down")
        db.execute_one.side_effect = [
            {"next_ver": 1},
            {"id": 1, "version": 1, "status": "draft", "created_at": now},
        ]

        # Should not raise despite event bus failure
        result = mgr.create(work_item_id=42, summary="Test")
        assert result["id"] == 1

    def test_row_to_dict_handles_string_json(self):
        mgr, db, _ = self._make_manager()
        now = datetime.now(timezone.utc)
        db.execute_one.return_value = {
            "id": 1, "work_item_id": 42, "version": 1,
            "status": "draft", "summary": "Test",
            "changes": '[]',  # string instead of list
            "decisions": '[]',
            "open_items": '[]',
            "metrics": '{}',
            "reviewer_notes": None, "reviewed_by": None,
            "reviewed_at": None, "created_at": now, "updated_at": now,
        }

        result = mgr.get(42)

        assert isinstance(result["changes"], list)
        assert isinstance(result["metrics"], dict)


class TestDeliverableStatus:
    def test_reviewable_states(self):
        assert DeliverableStatus.DRAFT in DeliverableStatus.REVIEWABLE
        assert DeliverableStatus.PENDING_REVIEW in DeliverableStatus.REVIEWABLE

    def test_terminal_states(self):
        assert DeliverableStatus.APPROVED in DeliverableStatus.TERMINAL
        assert DeliverableStatus.REVISED in DeliverableStatus.TERMINAL
        assert DeliverableStatus.REJECTED in DeliverableStatus.TERMINAL

    def test_all_states(self):
        assert len(DeliverableStatus.ALL) == 5
