"""Tests for cairn.core.subscriptions and cairn.listeners.notification_listener."""

from unittest.mock import MagicMock, call

from cairn.core.subscriptions import SubscriptionManager
from cairn.listeners.notification_listener import NotificationListener


class TestSubscriptionManager:
    def _make_manager(self):
        db = MagicMock()
        return SubscriptionManager(db), db

    def test_create_subscription(self):
        sm, db = self._make_manager()
        db.execute_one.return_value = {
            "id": 1, "name": "review-alerts", "patterns": ["deliverable.*"],
            "channel": "in_app", "channel_config": {}, "project_id": None,
            "is_active": True, "created_at": "2026-01-01T00:00:00",
        }

        result = sm.create(name="review-alerts", patterns=["deliverable.*"])
        assert result["id"] == 1
        assert result["name"] == "review-alerts"
        db.commit.assert_called()

    def test_list_subscriptions(self):
        sm, db = self._make_manager()
        db.execute.return_value = [
            {"id": 1, "name": "s1", "patterns": ["*"], "channel": "in_app",
             "channel_config": {}, "project_id": None, "project_name": None,
             "is_active": True, "created_at": "2026-01-01T00:00:00",
             "updated_at": "2026-01-01T00:00:00"},
        ]
        result = sm.list()
        assert len(result) == 1

    def test_update_subscription(self):
        sm, db = self._make_manager()
        db.execute_one.return_value = {
            "id": 1, "name": "updated", "patterns": ["work_item.*"],
            "channel": "in_app", "channel_config": {}, "project_id": None,
            "project_name": None, "is_active": True,
            "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
        }
        result = sm.update(1, name="updated")
        assert result["name"] == "updated"

    def test_delete_deactivates(self):
        sm, db = self._make_manager()
        result = sm.delete(1)
        assert result["action"] == "deactivated"
        db.commit.assert_called()

    def test_find_matching_exact(self):
        sm, db = self._make_manager()
        db.execute.return_value = [
            {"id": 1, "name": "s1", "patterns": ["work_item.completed"],
             "channel": "in_app", "channel_config": {}, "project_id": None,
             "project_name": None, "is_active": True,
             "created_at": "2026-01-01T00:00:00", "updated_at": None},
        ]
        matched = sm.find_matching("work_item.completed")
        assert len(matched) == 1

    def test_find_matching_wildcard(self):
        sm, db = self._make_manager()
        db.execute.return_value = [
            {"id": 1, "name": "s1", "patterns": ["work_item.*"],
             "channel": "in_app", "channel_config": {}, "project_id": None,
             "project_name": None, "is_active": True,
             "created_at": "2026-01-01T00:00:00", "updated_at": None},
        ]
        matched = sm.find_matching("work_item.completed")
        assert len(matched) == 1

    def test_find_matching_global_wildcard(self):
        sm, db = self._make_manager()
        db.execute.return_value = [
            {"id": 1, "name": "all", "patterns": ["*"],
             "channel": "in_app", "channel_config": {}, "project_id": None,
             "project_name": None, "is_active": True,
             "created_at": "2026-01-01T00:00:00", "updated_at": None},
        ]
        matched = sm.find_matching("anything.here")
        assert len(matched) == 1

    def test_find_matching_no_match(self):
        sm, db = self._make_manager()
        db.execute.return_value = [
            {"id": 1, "name": "s1", "patterns": ["memory.*"],
             "channel": "in_app", "channel_config": {}, "project_id": None,
             "project_name": None, "is_active": True,
             "created_at": "2026-01-01T00:00:00", "updated_at": None},
        ]
        matched = sm.find_matching("work_item.completed")
        assert len(matched) == 0

    def test_find_matching_with_filter_suffix(self):
        """Pattern 'work_item.gated:project=cairn' should match 'work_item.gated'."""
        sm, db = self._make_manager()
        db.execute.return_value = [
            {"id": 1, "name": "s1", "patterns": ["work_item.gated:project=cairn"],
             "channel": "in_app", "channel_config": {}, "project_id": None,
             "project_name": None, "is_active": True,
             "created_at": "2026-01-01T00:00:00", "updated_at": None},
        ]
        matched = sm.find_matching("work_item.gated")
        assert len(matched) == 1

    def test_create_notification(self):
        sm, db = self._make_manager()
        db.execute_one.return_value = {
            "id": 1, "title": "Test", "severity": "info",
            "is_read": False, "created_at": "2026-01-01T00:00:00",
        }
        result = sm.create_notification(
            subscription_id=1, event_id=100,
            title="Test", body="body", severity="info",
        )
        assert result["id"] == 1
        assert result["is_read"] is False

    def test_list_notifications(self):
        sm, db = self._make_manager()
        db.execute.return_value = [
            {"id": 1, "title": "N1", "severity": "info", "is_read": False,
             "created_at": "2026-01-01T00:00:00", "read_at": None,
             "subscription_id": 1, "event_id": 100, "body": None, "metadata": {}},
        ]
        db.execute_one.side_effect = [
            {"total": 1},  # total count
            {"total": 1},  # unread count
        ]
        result = sm.list_notifications()
        assert result["total"] == 1
        assert result["unread"] == 1
        assert len(result["items"]) == 1

    def test_mark_read(self):
        sm, db = self._make_manager()
        result = sm.mark_read(1)
        assert result["is_read"] is True

    def test_mark_all_read(self):
        sm, db = self._make_manager()
        db.execute.return_value = [{"id": 1}, {"id": 2}]
        result = sm.mark_all_read()
        assert result["marked"] == 2

    def test_unread_count(self):
        sm, db = self._make_manager()
        db.execute_one.return_value = {"total": 5}
        assert sm.unread_count() == 5

    def test_notify_for_event_creates_in_app(self):
        sm, db = self._make_manager()
        # find_matching returns one in_app subscription
        db.execute.return_value = [
            {"id": 1, "name": "review", "patterns": ["deliverable.*"],
             "channel": "in_app", "channel_config": {}, "project_id": None,
             "project_name": None, "is_active": True,
             "created_at": "2026-01-01T00:00:00", "updated_at": None},
        ]
        # create_notification
        db.execute_one.return_value = {
            "id": 10, "title": "Deliverable ready for review",
            "severity": "info", "is_read": False, "created_at": "2026-01-01T00:00:00",
        }

        created = sm.notify_for_event({
            "event_type": "deliverable.created",
            "event_id": 100,
            "project_id": None,
            "payload": {"work_item_id": 42},
        })
        assert created == 1

    def test_notify_for_event_skips_non_in_app(self):
        sm, db = self._make_manager()
        db.execute.return_value = [
            {"id": 1, "name": "webhook-sub", "patterns": ["*"],
             "channel": "webhook", "channel_config": {"url": "http://example.com"},
             "project_id": None, "project_name": None, "is_active": True,
             "created_at": "2026-01-01T00:00:00", "updated_at": None},
        ]
        created = sm.notify_for_event({
            "event_type": "work_item.completed",
            "event_id": 100,
            "project_id": None,
            "payload": {},
        })
        assert created == 0

    def test_build_title_with_payload_title(self):
        sm, _ = self._make_manager()
        title = sm._build_title("work_item.completed", {"title": "Fix the widget"})
        assert "Fix the widget" in title

    def test_build_title_fallback(self):
        sm, _ = self._make_manager()
        title = sm._build_title("custom.event", {})
        assert "Custom Event" in title


class TestNotificationListener:
    def _make_listener(self):
        sm = MagicMock()
        return NotificationListener(sm), sm

    def test_register_subscribes_to_all(self):
        listener, _ = self._make_listener()
        bus = MagicMock()
        listener.register(bus)
        bus.subscribe.assert_called_once_with("*", "notification_dispatch", listener.handle)

    def test_handle_calls_notify_for_event(self):
        listener, sm = self._make_listener()
        sm.notify_for_event.return_value = 2
        listener.handle({"event_type": "work_item.completed", "event_id": 1, "payload": {}})
        sm.notify_for_event.assert_called_once()

    def test_handle_skips_session_events(self):
        listener, sm = self._make_listener()
        listener.handle({"event_type": "session_start", "event_id": 1})
        sm.notify_for_event.assert_not_called()

    def test_handle_skips_empty_event_type(self):
        listener, sm = self._make_listener()
        listener.handle({"event_type": "", "event_id": 1})
        sm.notify_for_event.assert_not_called()

    def test_exception_does_not_propagate(self):
        listener, sm = self._make_listener()
        sm.notify_for_event.side_effect = Exception("DB down")
        # Should not raise
        listener.handle({"event_type": "work_item.completed", "event_id": 1})
