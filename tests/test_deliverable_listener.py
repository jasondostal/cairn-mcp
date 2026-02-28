"""Tests for cairn.listeners.deliverable_listener.DeliverableListener."""

import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from cairn.listeners.deliverable_listener import DeliverableListener


class TestDeliverableListener:
    def _make_listener(self, with_llm=False):
        dm = MagicMock()
        wim = MagicMock()
        db = MagicMock()
        llm = MagicMock() if with_llm else None
        listener = DeliverableListener(
            deliverable_manager=dm,
            work_item_manager=wim,
            db=db,
            llm=llm,
        )
        return listener, dm, wim, db, llm

    def test_register_subscribes_to_completed(self):
        listener, *_ = self._make_listener()
        event_bus = MagicMock()
        listener.register(event_bus)
        event_bus.subscribe.assert_called_once_with(
            "work_item.completed", "deliverable_auto_gen", listener.handle,
        )

    def test_handle_skips_if_no_work_item_id(self):
        listener, dm, *_ = self._make_listener()
        listener.handle({"payload": {}})
        dm.create.assert_not_called()

    def test_handle_skips_if_deliverable_exists(self):
        listener, dm, wim, *_ = self._make_listener()
        dm.get.return_value = {"id": 1, "version": 1}

        listener.handle({"payload": {"work_item_id": 42}})

        dm.get.assert_called_once_with(42)
        dm.create.assert_not_called()

    def test_mechanical_generation_without_llm(self):
        listener, dm, wim, db, _ = self._make_listener(with_llm=False)
        dm.get.return_value = None  # no existing deliverable

        wim.get.return_value = {
            "id": 42, "title": "Fix the widget", "description": "It's broken",
        }
        wim.get_activity.return_value = {
            "activities": [
                {"activity_type": "created", "content": "Created", "actor": "agent-1"},
                {"activity_type": "checkpoint", "content": "Fixed the handler", "actor": "agent-1"},
                {"activity_type": "status_change", "content": "open -> in_progress", "actor": "agent-1"},
            ]
        }
        db.execute.return_value = []  # no linked memories

        listener.handle({"payload": {"work_item_id": 42}})

        dm.create.assert_called_once()
        call_kwargs = dm.create.call_args[1]
        assert call_kwargs["work_item_id"] == 42
        assert "Fix the widget" in call_kwargs["summary"]
        assert call_kwargs["status"] == "pending_review"
        # Checkpoint content should appear in changes
        assert any("Fixed the handler" in c["description"] for c in call_kwargs["changes"])

    def test_llm_generation(self):
        listener, dm, wim, db, llm = self._make_listener(with_llm=True)
        dm.get.return_value = None

        wim.get.return_value = {
            "id": 42, "title": "Add auth", "description": "JWT auth for API",
        }
        wim.get_activity.return_value = {
            "activities": [
                {"activity_type": "checkpoint", "content": "Added JWT middleware", "actor": "agent-1"},
            ]
        }
        db.execute.return_value = []

        llm.generate.return_value = json.dumps({
            "summary": "Added JWT authentication middleware to all API routes.",
            "changes": [{"description": "New auth middleware", "type": "code"}],
            "decisions": [{"decision": "Used HS256", "rationale": "Simpler, sufficient for single-server"}],
            "open_items": [],
        })

        listener.handle({"payload": {"work_item_id": 42}})

        dm.create.assert_called_once()
        call_kwargs = dm.create.call_args[1]
        assert "JWT" in call_kwargs["summary"]
        assert len(call_kwargs["changes"]) == 1
        assert len(call_kwargs["decisions"]) == 1

    def test_llm_bad_json_falls_back_to_mechanical(self):
        listener, dm, wim, db, llm = self._make_listener(with_llm=True)
        dm.get.return_value = None

        wim.get.return_value = {
            "id": 42, "title": "Do stuff", "description": "Things",
        }
        wim.get_activity.return_value = {"activities": []}
        db.execute.return_value = []

        llm.generate.return_value = "This is not JSON at all"

        listener.handle({"payload": {"work_item_id": 42}})

        # Should still create a mechanical deliverable
        dm.create.assert_called_once()
        call_kwargs = dm.create.call_args[1]
        assert call_kwargs["status"] == "pending_review"

    def test_exception_in_generate_does_not_propagate(self):
        listener, dm, wim, *_ = self._make_listener()
        dm.get.return_value = None
        wim.get.side_effect = Exception("DB down")

        # Should not raise
        listener.handle({"payload": {"work_item_id": 42}})

    def test_linked_memories_included(self):
        listener, dm, wim, db, llm = self._make_listener(with_llm=True)
        dm.get.return_value = None

        wim.get.return_value = {"id": 42, "title": "Task", "description": "Desc"}
        wim.get_activity.return_value = {"activities": []}
        db.execute.return_value = [
            {"id": 1, "content": "Important finding", "memory_type": "learning",
             "importance": 0.8, "summary": "We learned X"},
        ]

        llm.generate.return_value = json.dumps({
            "summary": "Done", "changes": [], "decisions": [], "open_items": [],
        })

        listener.handle({"payload": {"work_item_id": 42}})

        # Verify LLM prompt included memory
        prompt = llm.generate.call_args[0][0]
        assert "We learned X" in prompt

    def test_metrics_computed(self):
        listener, dm, wim, db, _ = self._make_listener(with_llm=False)
        dm.get.return_value = None

        wim.get.return_value = {"id": 42, "title": "Task", "description": ""}
        wim.get_activity.return_value = {
            "activities": [
                {"activity_type": "heartbeat", "content": "working", "actor": "a"},
                {"activity_type": "heartbeat", "content": "working", "actor": "a"},
                {"activity_type": "checkpoint", "content": "milestone", "actor": "a"},
                {"activity_type": "status_change", "content": "change", "actor": "a"},
            ]
        }
        db.execute.return_value = []

        listener.handle({"payload": {"work_item_id": 42}})

        call_kwargs = dm.create.call_args[1]
        assert call_kwargs["metrics"]["heartbeat_count"] == 2
        assert call_kwargs["metrics"]["checkpoint_count"] == 1
        assert call_kwargs["metrics"]["total_activities"] == 4
