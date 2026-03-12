"""Tests for settings governance — env-locked detection and audit events (ca-135)."""

from unittest.mock import MagicMock, patch
import pytest

from cairn.config import EDITABLE_KEYS


class TestEnvLockedResponse:
    """Settings response includes env_locked list."""

    def test_env_locked_in_response(self):
        """Keys set via env vars appear in env_locked."""
        from cairn.config import config_to_flat, env_values
        from cairn.storage import settings_store

        # Simulate: env_values returns a snapshot where audit.enabled is set
        fake_env = {"audit.enabled": "true"}

        svc = MagicMock()
        svc.db = MagicMock()
        svc.config = MagicMock()
        svc.config.profile = None
        svc.event_bus = None

        with patch("cairn.api.core.env_values", return_value=fake_env), \
             patch("cairn.api.core.config_to_flat", return_value={"audit.enabled": True, "llm.backend": "ollama"}), \
             patch("cairn.api.core.settings_store") as mock_store:
            mock_store.load_all.return_value = {}

            from cairn.api.core import register_routes
            from fastapi import APIRouter
            router = APIRouter()
            register_routes(router, svc)

            # Find the GET /settings route handler
            for route in router.routes:
                if hasattr(route, "path") and route.path == "/settings" and "GET" in getattr(route, "methods", set()):
                    response = route.endpoint()
                    assert "env_locked" in response
                    assert "audit.enabled" in response["env_locked"]
                    assert "llm.backend" not in response["env_locked"]
                    return
            pytest.fail("GET /settings route not found")

    def test_env_locked_rejects_update(self):
        """PATCH to an env-locked key returns 409."""
        from fastapi import HTTPException

        fake_env = {"llm.backend": "bedrock"}

        svc = MagicMock()
        svc.db = MagicMock()
        svc.config = MagicMock()
        svc.config.profile = None
        svc.event_bus = None

        # Mock admin user so the require_admin() check passes
        fake_admin = MagicMock()
        fake_admin.role = "admin"

        with patch("cairn.api.core.env_values", return_value=fake_env), \
             patch("cairn.api.core.config_to_flat", return_value={"llm.backend": "bedrock"}), \
             patch("cairn.api.core.settings_store") as mock_store, \
             patch("cairn.core.user.current_user", return_value=fake_admin):
            mock_store.load_all.return_value = {}

            from cairn.api.core import register_routes
            from fastapi import APIRouter
            router = APIRouter()
            register_routes(router, svc)

            # Find the PATCH /settings route handler
            for route in router.routes:
                if hasattr(route, "path") and route.path == "/settings" and "PATCH" in getattr(route, "methods", set()):
                    with pytest.raises(HTTPException) as exc_info:
                        route.endpoint({"llm.backend": "ollama"})
                    assert exc_info.value.status_code == 409
                    assert "env-locked" in str(exc_info.value.detail)
                    return
            pytest.fail("PATCH /settings route not found")


class TestSettingsAuditEvent:
    """Settings changes emit audit events."""

    def test_settings_change_emits_event(self):
        """Successful PATCH emits settings.updated event."""
        fake_env = {}

        svc = MagicMock()
        svc.db = MagicMock()
        svc.config = MagicMock()
        svc.config.profile = None
        svc.event_bus = MagicMock()

        with patch("cairn.api.core.env_values", return_value=fake_env), \
             patch("cairn.api.core.config_to_flat", return_value={"llm.backend": "ollama"}), \
             patch("cairn.api.core.settings_store") as mock_store:
            mock_store.load_all.return_value = {}

            from cairn.api.core import register_routes
            from cairn.core.user import set_user, clear_user, UserContext
            from fastapi import APIRouter
            router = APIRouter()
            register_routes(router, svc)

            # Set a user context
            set_user(UserContext(user_id=1, username="admin", role="admin"))
            try:
                for route in router.routes:
                    if hasattr(route, "path") and route.path == "/settings" and "PATCH" in getattr(route, "methods", set()):
                        route.endpoint({"llm.backend": "bedrock"})
                        # Verify event was published
                        svc.event_bus.emit.assert_called_once()
                        call_kwargs = svc.event_bus.emit.call_args
                        assert call_kwargs[0][0] == "settings.updated"
                        assert call_kwargs[1]["payload"]["user"] == "admin"
                        assert "llm.backend" in call_kwargs[1]["payload"]["changes"]
                        return
                pytest.fail("PATCH /settings route not found")
            finally:
                clear_user()


class TestWebhookEditableKeys:
    """Verify webhook sub-keys are in EDITABLE_KEYS."""

    @pytest.mark.parametrize("key", [
        "webhooks.delivery_interval",
        "webhooks.delivery_batch_size",
        "webhooks.max_attempts",
        "webhooks.backoff_base",
        "webhooks.timeout",
    ])
    def test_webhook_key_editable(self, key):
        assert key in EDITABLE_KEYS
