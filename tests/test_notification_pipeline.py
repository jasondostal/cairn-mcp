"""Tests for the gate notification pipeline: event → subscription → push → click_url.

Verifies the full chain from gate_set event through subscription matching,
notification body generation, click URL construction, and push dispatch.

Part of ca-259: ntfy deep link → gate response mobile flow.
"""

from unittest.mock import MagicMock, call, patch

from cairn.core.subscriptions import SubscriptionManager


# ---------------------------------------------------------------------------
# Click URL generation
# ---------------------------------------------------------------------------


class TestBuildClickUrl:
    def _make_manager(self):
        db = MagicMock()
        return SubscriptionManager(db), db

    def test_click_url_with_display_id(self):
        sm, _ = self._make_manager()
        url = sm._build_click_url(
            "work_item.gate_set",
            {"payload": {"display_id": "ca-42"}},
            {"base_url": "https://cairn.example.com"},
        )
        assert url == "https://cairn.example.com/work/ca-42"

    def test_click_url_falls_back_to_work_item_id(self):
        sm, _ = self._make_manager()
        url = sm._build_click_url(
            "work_item.gate_set",
            {"work_item_id": 42, "payload": {}},
            {"base_url": "https://cairn.example.com"},
        )
        assert url == "https://cairn.example.com/work/42"

    def test_click_url_none_without_base_url(self):
        sm, _ = self._make_manager()
        url = sm._build_click_url(
            "work_item.gate_set",
            {"payload": {"display_id": "ca-42"}},
            {},
        )
        assert url is None

    def test_click_url_none_for_non_work_item_events(self):
        sm, _ = self._make_manager()
        url = sm._build_click_url(
            "memory.created",
            {"payload": {}},
            {"base_url": "https://cairn.example.com"},
        )
        assert url is None

    def test_click_url_strips_trailing_slash(self):
        sm, _ = self._make_manager()
        url = sm._build_click_url(
            "work_item.completed",
            {"payload": {"display_id": "ca-10"}},
            {"base_url": "https://cairn.example.com/"},
        )
        assert url == "https://cairn.example.com/work/ca-10"


# ---------------------------------------------------------------------------
# Gate event notification body
# ---------------------------------------------------------------------------


class TestBuildBody:
    def _make_manager(self):
        db = MagicMock()
        return SubscriptionManager(db), db

    def test_gate_body_shows_question(self):
        sm, _ = self._make_manager()
        body = sm._build_body("work_item.gate_set", {
            "gate_data": {"question": "Should I refactor the auth module?"},
        })
        assert "Should I refactor the auth module?" in body

    def test_gate_body_shows_options(self):
        sm, _ = self._make_manager()
        body = sm._build_body("work_item.gate_set", {
            "gate_data": {
                "question": "Proceed?",
                "options": ["yes", "no", "skip"],
            },
        })
        assert "yes" in body
        assert "no" in body
        assert "skip" in body

    def test_gate_body_none_without_gate_data(self):
        sm, _ = self._make_manager()
        body = sm._build_body("work_item.gate_set", {})
        assert body is None

    def test_non_gate_body_uses_summary(self):
        sm, _ = self._make_manager()
        body = sm._build_body("work_item.completed", {
            "summary": "Finished the widget refactor",
        })
        assert "Finished the widget refactor" in body


# ---------------------------------------------------------------------------
# Gate title generation
# ---------------------------------------------------------------------------


class TestBuildTitle:
    def _make_manager(self):
        db = MagicMock()
        return SubscriptionManager(db), db

    def test_gate_set_uses_template(self):
        sm, _ = self._make_manager()
        title = sm._build_title("work_item.gate_set", {})
        assert "input" in title.lower() or "gate" in title.lower()

    def test_gate_set_appends_payload_title(self):
        sm, _ = self._make_manager()
        title = sm._build_title("work_item.gate_set", {"title": "Refactor auth"})
        assert "Refactor auth" in title

    def test_gate_resolved_uses_template(self):
        sm, _ = self._make_manager()
        title = sm._build_title("work_item.gate_resolved", {})
        assert "resolved" in title.lower() or "gate" in title.lower()


# ---------------------------------------------------------------------------
# Push channel dispatch
# ---------------------------------------------------------------------------


class TestPushChannelDispatch:
    def _make_manager_with_push(self):
        db = MagicMock()
        push = MagicMock()
        push.enabled = True
        push.send.return_value = True
        return SubscriptionManager(db, push_notifier=push), db, push

    def test_push_subscription_sends_notification(self):
        sm, db, push = self._make_manager_with_push()

        # find_matching returns one push subscription with base_url
        db.execute.return_value = [
            {
                "id": 1, "name": "gate-push", "patterns": ["work_item.gate_set"],
                "channel": "push",
                "channel_config": {
                    "topic": "cairn-gates",
                    "base_url": "https://cairn.example.com",
                },
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        created = sm.notify_for_event({
            "event_type": "work_item.gate_set",
            "event_id": 100,
            "project_id": None,
            "payload": {
                "gate_data": {"question": "Proceed?"},
                "display_id": "ca-42",
                "title": "Fix the widget",
            },
        })

        assert created == 1
        push.send.assert_called_once()
        call_kwargs = push.send.call_args.kwargs
        assert call_kwargs["topic"] == "cairn-gates"
        assert call_kwargs["click_url"] == "https://cairn.example.com/work/ca-42"
        assert "input" in call_kwargs["title"].lower() or "gate" in call_kwargs["title"].lower()
        assert call_kwargs["severity"] == "warning"

    def test_push_not_sent_when_notifier_disabled(self):
        sm, db, push = self._make_manager_with_push()
        push.enabled = False

        db.execute.return_value = [
            {
                "id": 1, "name": "push-sub", "patterns": ["work_item.*"],
                "channel": "push", "channel_config": {"topic": "test"},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        created = sm.notify_for_event({
            "event_type": "work_item.gate_set",
            "event_id": 100,
            "project_id": None,
            "payload": {},
        })

        assert created == 0
        push.send.assert_not_called()

    def test_push_not_counted_when_send_fails(self):
        sm, db, push = self._make_manager_with_push()
        push.send.return_value = False  # Send failed

        db.execute.return_value = [
            {
                "id": 1, "name": "push-sub", "patterns": ["*"],
                "channel": "push", "channel_config": {"topic": "test"},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        created = sm.notify_for_event({
            "event_type": "work_item.gate_set",
            "event_id": 100,
            "project_id": None,
            "payload": {},
        })

        assert created == 0

    def test_in_app_and_push_both_fire(self):
        """A gate event with both in_app and push subscriptions creates both."""
        sm, db, push = self._make_manager_with_push()

        db.execute.return_value = [
            {
                "id": 1, "name": "in-app", "patterns": ["work_item.*"],
                "channel": "in_app", "channel_config": {},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
            {
                "id": 2, "name": "push", "patterns": ["work_item.*"],
                "channel": "push",
                "channel_config": {"topic": "gates", "base_url": "https://cairn.example.com"},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        # Mock create_notification for in_app
        db.execute_one.return_value = {
            "id": 10, "title": "Agent needs input", "severity": "warning",
            "is_read": False, "created_at": "2026-01-01T00:00:00",
        }

        created = sm.notify_for_event({
            "event_type": "work_item.gate_set",
            "event_id": 100,
            "project_id": None,
            "payload": {
                "gate_data": {"question": "Proceed?"},
                "display_id": "ca-42",
            },
        })

        assert created == 2  # one in_app + one push
        push.send.assert_called_once()
        db.commit.assert_called()  # in_app notification committed


# ---------------------------------------------------------------------------
# Severity mapping for gate events
# ---------------------------------------------------------------------------


class TestSeverityMapping:
    def _make_manager_with_push(self):
        db = MagicMock()
        push = MagicMock()
        push.enabled = True
        push.send.return_value = True
        return SubscriptionManager(db, push_notifier=push), db, push

    def test_gate_set_is_warning_severity(self):
        sm, db, push = self._make_manager_with_push()
        db.execute.return_value = [
            {
                "id": 1, "name": "push", "patterns": ["*"],
                "channel": "push", "channel_config": {"topic": "t"},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        sm.notify_for_event({
            "event_type": "work_item.gate_set",
            "event_id": 1, "project_id": None, "payload": {},
        })

        assert push.send.call_args.kwargs["severity"] == "warning"

    def test_gate_resolved_is_success_severity(self):
        sm, db, push = self._make_manager_with_push()
        db.execute.return_value = [
            {
                "id": 1, "name": "push", "patterns": ["*"],
                "channel": "push", "channel_config": {"topic": "t"},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        sm.notify_for_event({
            "event_type": "work_item.gate_resolved",
            "event_id": 1, "project_id": None, "payload": {},
        })

        assert push.send.call_args.kwargs["severity"] == "success"
