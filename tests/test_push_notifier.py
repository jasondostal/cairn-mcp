"""Tests for cairn.listeners.push_notifier and push-channel subscription flow."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from cairn.listeners.push_notifier import PushNotifier, _PRIORITY_MAP, _TAG_MAP


@dataclass(frozen=True)
class FakePushConfig:
    enabled: bool = True
    url: str = "https://ntfy.example.com"
    token: str = "test-token-123"
    default_topic: str = "cairn"
    timeout: int = 5


class TestPushNotifier:
    def _make_notifier(self, **overrides):
        config = FakePushConfig(**overrides)
        return PushNotifier(config)

    def test_enabled_when_url_and_enabled(self):
        pn = self._make_notifier()
        assert pn.enabled is True

    def test_disabled_when_flag_false(self):
        pn = self._make_notifier(enabled=False)
        assert pn.enabled is False

    def test_disabled_when_no_url(self):
        pn = self._make_notifier(url="")
        assert pn.enabled is False

    def test_send_disabled_returns_false(self):
        pn = self._make_notifier(enabled=False)
        assert pn.send(title="test") is False

    @patch("cairn.listeners.push_notifier.httpx.Client")
    def test_send_success(self, MockClient):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        MockClient.return_value = mock_client

        pn = self._make_notifier()
        result = pn.send(title="Agent done", body="Task completed", severity="success")

        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "cairn" in call_args[1].get("url", "") or "cairn" in call_args[0][0]
        headers = call_args[1].get("headers", {})
        assert headers["Title"] == "Agent done"
        assert headers["Priority"] == "3"  # success = default priority

    @patch("cairn.listeners.push_notifier.httpx.Client")
    def test_send_with_error_severity_high_priority(self, MockClient):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        MockClient.return_value = mock_client

        pn = self._make_notifier()
        pn.send(title="Agent stuck", severity="error")

        headers = mock_client.post.call_args[1]["headers"]
        assert headers["Priority"] == "5"  # error = max priority

    @patch("cairn.listeners.push_notifier.httpx.Client")
    def test_send_with_warning_severity(self, MockClient):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        MockClient.return_value = mock_client

        pn = self._make_notifier()
        pn.send(title="Gate hit", severity="warning")

        headers = mock_client.post.call_args[1]["headers"]
        assert headers["Priority"] == "4"  # warning = high priority

    @patch("cairn.listeners.push_notifier.httpx.Client")
    def test_send_with_custom_topic(self, MockClient):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        MockClient.return_value = mock_client

        pn = self._make_notifier()
        pn.send(title="Alert", topic="cairn-alerts")

        url = mock_client.post.call_args[0][0]
        assert "cairn-alerts" in url

    @patch("cairn.listeners.push_notifier.httpx.Client")
    def test_send_with_click_url(self, MockClient):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        MockClient.return_value = mock_client

        pn = self._make_notifier()
        pn.send(title="Review", click_url="https://cairn.example.com/work-items?open=42")

        headers = mock_client.post.call_args[1]["headers"]
        assert headers["Click"] == "https://cairn.example.com/work-items?open=42"

    @patch("cairn.listeners.push_notifier.httpx.Client")
    def test_send_includes_tags(self, MockClient):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        MockClient.return_value = mock_client

        pn = self._make_notifier()
        pn.send(title="Test", severity="warning", tags=["custom"])

        headers = mock_client.post.call_args[1]["headers"]
        assert "warning" in headers["Tags"]
        assert "custom" in headers["Tags"]

    @patch("cairn.listeners.push_notifier.httpx.Client")
    def test_send_auth_header(self, MockClient):
        MockClient.return_value = MagicMock()

        pn = self._make_notifier(token="my-secret")
        pn._get_client()

        call_kwargs = MockClient.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer my-secret"

    @patch("cairn.listeners.push_notifier.httpx.Client")
    def test_send_no_auth_when_no_token(self, MockClient):
        MockClient.return_value = MagicMock()

        pn = self._make_notifier(token="")
        pn._get_client()

        call_kwargs = MockClient.call_args[1]
        assert "Authorization" not in call_kwargs["headers"]

    @patch("cairn.listeners.push_notifier.httpx.Client")
    def test_send_failure_returns_false(self, MockClient):
        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("Connection refused")
        MockClient.return_value = mock_client

        pn = self._make_notifier()
        result = pn.send(title="Test")

        assert result is False

    @patch("cairn.listeners.push_notifier.httpx.Client")
    def test_send_http_error_returns_false(self, MockClient):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("403 Forbidden")
        mock_client.post.return_value = mock_resp
        MockClient.return_value = mock_client

        pn = self._make_notifier()
        result = pn.send(title="Test")

        assert result is False

    def test_close(self):
        pn = self._make_notifier()
        pn._client = MagicMock()
        pn.close()
        assert pn._client is None

    def test_title_truncation(self):
        """Title should be truncated to 256 chars for ntfy."""
        pn = self._make_notifier()
        with patch("cairn.listeners.push_notifier.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_resp
            MockClient.return_value = mock_client

            long_title = "A" * 300
            pn.send(title=long_title)

            headers = mock_client.post.call_args[1]["headers"]
            assert len(headers["Title"]) == 256


class TestPushChannelIntegration:
    """Test the push channel flow through SubscriptionManager."""

    def test_notify_for_event_sends_push(self):
        from cairn.core.subscriptions import SubscriptionManager

        db = MagicMock()
        push = MagicMock()
        push.enabled = True
        push.send.return_value = True

        sm = SubscriptionManager(db, push_notifier=push)

        # find_matching returns one push subscription
        db.execute.return_value = [
            {"id": 1, "name": "push-alerts", "patterns": ["work_item.*"],
             "channel": "push", "channel_config": {"topic": "cairn-work"},
             "project_id": None, "project_name": None, "is_active": True,
             "created_at": "2026-01-01T00:00:00", "updated_at": None},
        ]

        created = sm.notify_for_event({
            "event_type": "work_item.completed",
            "event_id": 100,
            "project_id": None,
            "payload": {"title": "Fix the widget"},
        })

        assert created == 1
        push.send.assert_called_once()
        call_kwargs = push.send.call_args[1]
        assert "Fix the widget" in call_kwargs["title"]
        assert call_kwargs["topic"] == "cairn-work"
        assert call_kwargs["severity"] == "success"

    def test_notify_for_event_skips_push_when_disabled(self):
        from cairn.core.subscriptions import SubscriptionManager

        db = MagicMock()
        push = MagicMock()
        push.enabled = False

        sm = SubscriptionManager(db, push_notifier=push)

        db.execute.return_value = [
            {"id": 1, "name": "push-alerts", "patterns": ["*"],
             "channel": "push", "channel_config": {},
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
        push.send.assert_not_called()

    def test_notify_for_event_no_push_notifier(self):
        from cairn.core.subscriptions import SubscriptionManager

        db = MagicMock()
        sm = SubscriptionManager(db)  # No push_notifier

        db.execute.return_value = [
            {"id": 1, "name": "push-alerts", "patterns": ["*"],
             "channel": "push", "channel_config": {},
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

    def test_mixed_channels_both_fire(self):
        """Both in_app and push subscriptions should be processed."""
        from cairn.core.subscriptions import SubscriptionManager

        db = MagicMock()
        push = MagicMock()
        push.enabled = True
        push.send.return_value = True

        sm = SubscriptionManager(db, push_notifier=push)

        db.execute.return_value = [
            {"id": 1, "name": "in-app-sub", "patterns": ["work_item.*"],
             "channel": "in_app", "channel_config": {},
             "project_id": None, "project_name": None, "is_active": True,
             "created_at": "2026-01-01T00:00:00", "updated_at": None},
            {"id": 2, "name": "push-sub", "patterns": ["work_item.*"],
             "channel": "push", "channel_config": {},
             "project_id": None, "project_name": None, "is_active": True,
             "created_at": "2026-01-01T00:00:00", "updated_at": None},
        ]
        # create_notification for the in_app channel
        db.execute_one.return_value = {
            "id": 10, "title": "Work item completed",
            "severity": "success", "is_read": False, "created_at": "2026-01-01T00:00:00",
        }

        created = sm.notify_for_event({
            "event_type": "work_item.completed",
            "event_id": 100,
            "project_id": None,
            "payload": {},
        })

        assert created == 2
        push.send.assert_called_once()
        db.execute_one.assert_called()  # in_app notification created


class TestPriorityMapping:
    def test_info_default_priority(self):
        assert _PRIORITY_MAP["info"] == 3

    def test_warning_high_priority(self):
        assert _PRIORITY_MAP["warning"] == 4

    def test_error_max_priority(self):
        assert _PRIORITY_MAP["error"] == 5

    def test_all_severities_mapped(self):
        for sev in ("info", "success", "warning", "error"):
            assert sev in _PRIORITY_MAP

    def test_all_severities_have_tags(self):
        for sev in ("info", "success", "warning", "error"):
            assert sev in _TAG_MAP
