"""Tests for cairn.listeners.review_listener.ReviewListener."""

from unittest.mock import MagicMock, call

from cairn.listeners.review_listener import ReviewListener, APPROVAL_IMPORTANCE_BOOST


class TestReviewListener:
    def _make_listener(self):
        wim = MagicMock()
        db = MagicMock()
        listener = ReviewListener(work_item_manager=wim, db=db)
        return listener, wim, db

    def test_register_subscribes_to_three_events(self):
        listener, *_ = self._make_listener()
        event_bus = MagicMock()
        listener.register(event_bus)
        assert event_bus.subscribe.call_count == 3
        event_types = [c[0][0] for c in event_bus.subscribe.call_args_list]
        assert "deliverable.approved" in event_types
        assert "deliverable.revised" in event_types
        assert "deliverable.rejected" in event_types

    def test_approved_boosts_memory_importance(self):
        listener, wim, db = self._make_listener()
        db.execute.return_value = [
            {"id": 1, "importance": 0.5, "tags": ["roadmap"]},
            {"id": 2, "importance": 0.9, "tags": []},
        ]

        listener._handle_approved({
            "payload": {"work_item_id": 42, "reviewer": "jason"},
        })

        # Should update both memories
        assert db.execute.call_count >= 3  # 1 SELECT + 2 UPDATEs
        db.commit.assert_called_once()

        # Check importance boost
        update_calls = [c for c in db.execute.call_args_list if "UPDATE memories" in str(c)]
        assert len(update_calls) == 2

    def test_approved_adds_human_verified_tag(self):
        listener, wim, db = self._make_listener()
        db.execute.return_value = [
            {"id": 1, "importance": 0.5, "tags": ["existing"]},
        ]

        listener._handle_approved({"payload": {"work_item_id": 42}})

        update_call = [c for c in db.execute.call_args_list if "UPDATE memories" in str(c)][0]
        tags_arg = update_call[0][1][1]  # second param = tags
        assert "human-verified" in tags_arg
        assert "existing" in tags_arg

    def test_approved_caps_importance_at_1(self):
        listener, wim, db = self._make_listener()
        db.execute.return_value = [
            {"id": 1, "importance": 0.95, "tags": []},
        ]

        listener._handle_approved({"payload": {"work_item_id": 42}})

        update_call = [c for c in db.execute.call_args_list if "UPDATE memories" in str(c)][0]
        importance_arg = update_call[0][1][0]
        assert importance_arg <= 1.0

    def test_revised_reopens_work_item(self):
        listener, wim, db = self._make_listener()
        wim.get.return_value = {
            "id": 42, "constraints": {"max_hours": 8},
        }
        db.execute_one.return_value = {"reviewer_notes": "Use the v2 API instead"}

        listener._handle_revised({
            "payload": {"work_item_id": 42, "version": 1, "reviewer": "jason"},
        })

        wim.update.assert_called_once()
        call_kwargs = wim.update.call_args[1]
        assert call_kwargs["status"] == "open"
        assert call_kwargs["assignee"] is None
        assert "revision_feedback" in call_kwargs["constraints"]
        assert call_kwargs["constraints"]["revision_feedback"] == "Use the v2 API instead"
        assert len(call_kwargs["constraints"]["revision_history"]) == 1

    def test_revised_preserves_existing_constraints(self):
        listener, wim, db = self._make_listener()
        wim.get.return_value = {
            "id": 42, "constraints": {"max_hours": 8, "no_deploy": True},
        }
        db.execute_one.return_value = {"reviewer_notes": "Fix it"}

        listener._handle_revised({"payload": {"work_item_id": 42}})

        constraints = wim.update.call_args[1]["constraints"]
        assert constraints["max_hours"] == 8
        assert constraints["no_deploy"] is True

    def test_revised_accumulates_revision_history(self):
        listener, wim, db = self._make_listener()
        wim.get.return_value = {
            "id": 42,
            "constraints": {
                "revision_history": [
                    {"version": 1, "reviewer": "jason", "feedback": "Wrong approach"},
                ],
            },
        }
        db.execute_one.return_value = {"reviewer_notes": "Better but still wrong"}

        listener._handle_revised({
            "payload": {"work_item_id": 42, "version": 2, "reviewer": "jason"},
        })

        constraints = wim.update.call_args[1]["constraints"]
        assert len(constraints["revision_history"]) == 2

    def test_rejected_cancels_work_item(self):
        listener, wim, db = self._make_listener()
        db.execute_one.return_value = {"reviewer_notes": "Completely wrong approach"}

        listener._handle_rejected({
            "payload": {"work_item_id": 42, "reviewer": "jason"},
        })

        wim.update.assert_called_once()
        assert wim.update.call_args[1]["status"] == "cancelled"
        wim._log_activity.assert_called_once()

    def test_handles_missing_work_item_id(self):
        listener, wim, db = self._make_listener()
        # Should not raise or call anything
        listener._handle_approved({"payload": {}})
        listener._handle_revised({"payload": {}})
        listener._handle_rejected({"payload": {}})
        wim.update.assert_not_called()

    def test_exception_does_not_propagate(self):
        listener, wim, db = self._make_listener()
        wim.get.side_effect = Exception("DB down")

        # Should not raise
        listener._handle_revised({"payload": {"work_item_id": 42}})
