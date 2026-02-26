"""Tests for cairn.core.webhooks, cairn.listeners.webhook_listener, and cairn.core.webhook_worker."""

import json
from unittest.mock import MagicMock, patch

from cairn.core.webhooks import (
    WebhookManager,
    _matches_pattern,
    generate_secret,
    sign_payload,
)
from cairn.listeners.webhook_listener import WebhookListener
from cairn.core.webhook_worker import WebhookDeliveryWorker


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------


class TestPatternMatching:
    def test_exact_match(self):
        assert _matches_pattern("memory.created", "memory.created") is True

    def test_exact_no_match(self):
        assert _matches_pattern("memory.created", "memory.updated") is False

    def test_wildcard_match(self):
        assert _matches_pattern("memory.created", "memory.*") is True
        assert _matches_pattern("work_item.completed", "work_item.*") is True

    def test_wildcard_no_match(self):
        assert _matches_pattern("memory.created", "work_item.*") is False

    def test_global_wildcard(self):
        assert _matches_pattern("memory.created", "*") is True
        assert _matches_pattern("anything.here", "*") is True

    def test_partial_domain_no_false_positive(self):
        assert _matches_pattern("memory_extra.created", "memory.*") is False

    def test_no_partial_suffix_match(self):
        assert _matches_pattern("memory.created_v2", "memory.created") is False


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------


class TestSigning:
    def test_generate_secret_length(self):
        secret = generate_secret()
        assert len(secret) == 64
        int(secret, 16)  # valid hex

    def test_generate_secret_unique(self):
        s1 = generate_secret()
        s2 = generate_secret()
        assert s1 != s2

    def test_sign_payload_deterministic(self):
        payload = b'{"test": true}'
        secret = "test-secret"
        sig1 = sign_payload(payload, secret)
        sig2 = sign_payload(payload, secret)
        assert sig1 == sig2

    def test_sign_payload_different_secret(self):
        payload = b'{"test": true}'
        sig1 = sign_payload(payload, "secret-a")
        sig2 = sign_payload(payload, "secret-b")
        assert sig1 != sig2

    def test_sign_payload_different_payload(self):
        secret = "same-secret"
        sig1 = sign_payload(b'{"a": 1}', secret)
        sig2 = sign_payload(b'{"b": 2}', secret)
        assert sig1 != sig2


# ---------------------------------------------------------------------------
# WebhookManager
# ---------------------------------------------------------------------------


class TestWebhookManager:
    def _make_manager(self):
        db = MagicMock()
        config = MagicMock()
        config.max_attempts = 5
        return WebhookManager(db, config), db

    def test_create_generates_secret(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {
            "id": 1, "project_id": None, "name": "test",
            "url": "https://example.com/hook", "secret": "generated",
            "event_types": ["memory.*"], "is_active": True,
            "metadata": {}, "created_at": None, "updated_at": None,
        }

        result = mgr.create(
            name="test",
            url="https://example.com/hook",
            event_types=["memory.*"],
        )

        assert result["id"] == 1
        db.execute_one.assert_called_once()
        db.commit.assert_called_once()
        # Verify a secret was passed (not None)
        params = db.execute_one.call_args[0][1]
        assert params[3] is not None
        assert len(params[3]) == 64

    def test_create_with_custom_secret(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {
            "id": 2, "project_id": None, "name": "test",
            "url": "https://example.com", "secret": "custom",
            "event_types": ["*"], "is_active": True,
            "metadata": {}, "created_at": None, "updated_at": None,
        }

        mgr.create(name="test", url="https://example.com",
                    event_types=["*"], secret="custom")

        params = db.execute_one.call_args[0][1]
        assert params[3] == "custom"

    def test_get_returns_dict(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {
            "id": 1, "project_id": None, "name": "hook1",
            "url": "https://a.com", "secret": "s1",
            "event_types": ["memory.*"], "is_active": True,
            "metadata": {}, "created_at": None, "updated_at": None,
        }

        result = mgr.get(1)
        assert result["id"] == 1
        assert result["event_types"] == ["memory.*"]

    def test_get_returns_none_when_missing(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = None
        assert mgr.get(999) is None

    def test_delete_returns_true(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {"id": 1}
        assert mgr.delete(1) is True
        db.commit.assert_called_once()

    def test_delete_returns_false_when_missing(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = None
        assert mgr.delete(999) is False

    def test_find_matching_webhooks_filters(self):
        mgr, db = self._make_manager()
        db.execute.return_value = [
            {
                "id": 1, "project_id": None, "name": "hook1",
                "url": "https://a.com", "secret": "s1",
                "event_types": ["memory.*"], "is_active": True,
                "metadata": {}, "created_at": None, "updated_at": None,
            },
            {
                "id": 2, "project_id": None, "name": "hook2",
                "url": "https://b.com", "secret": "s2",
                "event_types": ["work_item.*"], "is_active": True,
                "metadata": {}, "created_at": None, "updated_at": None,
            },
        ]

        matched = mgr.find_matching_webhooks("memory.created", project_id=None)
        assert len(matched) == 1
        assert matched[0]["id"] == 1

    def test_find_matching_global_wildcard(self):
        mgr, db = self._make_manager()
        db.execute.return_value = [
            {
                "id": 1, "project_id": None, "name": "catch-all",
                "url": "https://a.com", "secret": "s1",
                "event_types": ["*"], "is_active": True,
                "metadata": {}, "created_at": None, "updated_at": None,
            },
        ]

        matched = mgr.find_matching_webhooks("anything.here", project_id=None)
        assert len(matched) == 1

    def test_build_payload_includes_fields(self):
        mgr, _ = self._make_manager()
        event = {
            "event_id": 42,
            "event_type": "memory.created",
            "trace_id": "t123",
            "project_id": 1,
            "work_item_id": None,
            "session_name": "s1",
            "payload": {"memory_id": 7},
        }
        webhook = {"id": 1, "name": "test-hook"}

        result = mgr.build_payload(event, webhook)

        assert result["event_id"] == 42
        assert result["event_type"] == "memory.created"
        assert result["trace_id"] == "t123"
        assert result["webhook_id"] == 1
        assert result["webhook_name"] == "test-hook"
        assert "delivered_at" in result

    def test_create_delivery(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {"id": 100}

        result = mgr.create_delivery(
            webhook_id=1,
            event_id=42,
            request_body={"test": True},
        )

        assert result == 100
        db.commit.assert_called_once()

    def test_rotate_secret(self):
        mgr, db = self._make_manager()
        db.execute_one.return_value = {
            "id": 1, "project_id": None, "name": "hook1",
            "url": "https://a.com", "secret": "new-secret",
            "event_types": ["*"], "is_active": True,
            "metadata": {}, "created_at": None, "updated_at": None,
        }

        result = mgr.rotate_secret(1)
        assert result is not None
        db.commit.assert_called_once()
        # Verify new secret was passed
        params = db.execute_one.call_args[0][1]
        assert len(params[0]) == 64  # generated secret


# ---------------------------------------------------------------------------
# WebhookListener
# ---------------------------------------------------------------------------


class TestWebhookListener:
    def _make_listener(self):
        webhook_mgr = MagicMock()
        webhook_mgr.find_matching_webhooks.return_value = []
        webhook_mgr.build_payload.return_value = {"test": True}
        webhook_mgr.create_delivery.return_value = 1
        return WebhookListener(webhook_mgr), webhook_mgr

    def test_register_subscribes_to_all(self):
        listener, _ = self._make_listener()
        bus = MagicMock()
        listener.register(bus)
        bus.subscribe.assert_called_once_with("*", "webhook_dispatch", listener.handle)

    def test_handle_creates_delivery_for_match(self):
        listener, webhook_mgr = self._make_listener()
        webhook_mgr.find_matching_webhooks.return_value = [
            {"id": 1, "name": "hook1", "url": "https://a.com"},
        ]

        listener.handle({
            "event_type": "memory.created",
            "event_id": 42,
            "project_id": 1,
        })

        webhook_mgr.find_matching_webhooks.assert_called_once_with("memory.created", 1)
        webhook_mgr.build_payload.assert_called_once()
        webhook_mgr.create_delivery.assert_called_once()

    def test_handle_multiple_matches(self):
        listener, webhook_mgr = self._make_listener()
        webhook_mgr.find_matching_webhooks.return_value = [
            {"id": 1, "name": "hook1"},
            {"id": 2, "name": "hook2"},
        ]

        listener.handle({
            "event_type": "memory.created",
            "event_id": 42,
            "project_id": 1,
        })

        assert webhook_mgr.create_delivery.call_count == 2

    def test_handle_no_match_no_delivery(self):
        listener, webhook_mgr = self._make_listener()
        webhook_mgr.find_matching_webhooks.return_value = []

        listener.handle({
            "event_type": "memory.created",
            "event_id": 42,
            "project_id": 1,
        })

        webhook_mgr.create_delivery.assert_not_called()

    def test_handle_empty_event_type_skips(self):
        listener, webhook_mgr = self._make_listener()

        listener.handle({"event_type": "", "event_id": 1})
        listener.handle({})

        webhook_mgr.find_matching_webhooks.assert_not_called()

    def test_handle_missing_event_id_skips(self):
        listener, webhook_mgr = self._make_listener()

        listener.handle({"event_type": "memory.created"})

        webhook_mgr.find_matching_webhooks.assert_not_called()

    def test_handle_survives_webhook_lookup_error(self):
        listener, webhook_mgr = self._make_listener()
        webhook_mgr.find_matching_webhooks.side_effect = RuntimeError("db down")

        # Should not raise
        listener.handle({
            "event_type": "memory.created",
            "event_id": 42,
            "project_id": 1,
        })

    def test_handle_survives_delivery_creation_error(self):
        listener, webhook_mgr = self._make_listener()
        webhook_mgr.find_matching_webhooks.return_value = [
            {"id": 1, "name": "hook1"},
            {"id": 2, "name": "hook2"},
        ]
        webhook_mgr.create_delivery.side_effect = [
            RuntimeError("fail"), 2,
        ]

        # Should not raise — both attempted
        listener.handle({
            "event_type": "memory.created",
            "event_id": 42,
            "project_id": 1,
        })

        assert webhook_mgr.create_delivery.call_count == 2


# ---------------------------------------------------------------------------
# WebhookDeliveryWorker
# ---------------------------------------------------------------------------


class TestWebhookDeliveryWorker:
    def _make_worker(self):
        db = MagicMock()
        config = MagicMock()
        config.delivery_interval = 5.0
        config.delivery_batch_size = 20
        config.max_attempts = 5
        config.backoff_base = 30
        config.timeout = 10
        return WebhookDeliveryWorker(db, config), db

    def test_mark_success(self):
        worker, db = self._make_worker()

        worker._mark_success(1, 200, "OK")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "status = 'success'" in sql
        assert "response_status = %s" in sql
        db.commit.assert_called_once()

    def test_mark_failed_with_retry(self):
        worker, db = self._make_worker()
        db.execute_one.return_value = {"max_attempts": 5}

        worker._mark_failed(1, 0, "Connection error")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "status = 'failed'" in sql
        assert "next_retry" in sql
        db.commit.assert_called_once()

    def test_mark_failed_becomes_exhausted(self):
        worker, db = self._make_worker()
        db.execute_one.return_value = {"max_attempts": 5}

        worker._mark_failed(1, 4, "Still failing")  # attempt 4 -> next is 5 >= max

        # Should call _mark_exhausted which uses different SQL
        calls = db.execute.call_args_list
        sql = calls[0][0][0]
        assert "status = 'exhausted'" in sql

    def test_poll_empty_rolls_back(self):
        worker, db = self._make_worker()
        db.execute.return_value = []

        worker._poll()

        db.rollback.assert_called_once()
