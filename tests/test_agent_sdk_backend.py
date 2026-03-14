"""Tests for cairn.integrations.agent_sdk — Agent SDK backend.

Tests session lifecycle, risk tier mapping, event callbacks, health checks,
and the async query execution flow with a mocked claude-agent-sdk.
"""

import asyncio
import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cairn.integrations.agent_sdk import (
    AgentSDKBackend,
    AgentSDKConfig,
    _TIER_PERMISSION_MODE,
    _TIER_TOOLS,
    _cairn_mcp_tools,
)
from cairn.integrations.interface import WorkspaceBackendError


# ---------------------------------------------------------------------------
# Risk tier mapping
# ---------------------------------------------------------------------------


class TestRiskTierMapping:
    def test_tier_0_is_read_only(self):
        tools = _TIER_TOOLS[0]
        assert "Read" in tools
        assert "Grep" in tools
        assert "Edit" not in tools
        assert "Write" not in tools
        assert "Bash" not in tools

    def test_tier_1_adds_edits(self):
        tools = _TIER_TOOLS[1]
        assert "Edit" in tools
        assert "Write" in tools
        assert "Bash" not in tools

    def test_tier_2_adds_bash(self):
        tools = _TIER_TOOLS[2]
        assert "Bash" in tools
        assert "Agent" in tools

    def test_tier_3_full_autonomy(self):
        tools = _TIER_TOOLS[3]
        assert "Bash" in tools
        assert _TIER_PERMISSION_MODE[3] == "bypassPermissions"

    def test_permission_modes(self):
        assert _TIER_PERMISSION_MODE[0] == "plan"
        assert _TIER_PERMISSION_MODE[1] == "acceptEdits"
        assert _TIER_PERMISSION_MODE[2] == "acceptEdits"
        assert _TIER_PERMISSION_MODE[3] == "bypassPermissions"

    def test_cairn_mcp_tools_tier_0_read_only(self):
        tools = _cairn_mcp_tools(0)
        assert "mcp__cairn__orient" in tools
        assert "mcp__cairn__search" in tools
        assert "mcp__cairn__store" not in tools
        assert "mcp__cairn__work_items" not in tools

    def test_cairn_mcp_tools_tier_1_adds_store(self):
        tools = _cairn_mcp_tools(1)
        assert "mcp__cairn__store" in tools
        assert "mcp__cairn__work_items" in tools


# ---------------------------------------------------------------------------
# Backend lifecycle
# ---------------------------------------------------------------------------


class TestAgentSDKBackend:
    def _make_backend(self, **config_overrides):
        config = AgentSDKConfig(**config_overrides)
        return AgentSDKBackend(config)

    def test_backend_name(self):
        backend = self._make_backend()
        assert backend.backend_name() == "agent_sdk"

    def test_supports_capabilities(self):
        backend = self._make_backend()
        assert backend.supports_fork() is True
        assert backend.supports_abort() is True
        assert backend.supports_agents() is True

    def test_create_session(self):
        backend = self._make_backend()
        session = backend.create_session(title="test")
        assert session.id.startswith("sdk-")
        assert session.title == "test"

    def test_get_session(self):
        backend = self._make_backend()
        session = backend.create_session(title="test")
        retrieved = backend.get_session(session.id)
        assert retrieved.id == session.id

    def test_get_session_not_found(self):
        backend = self._make_backend()
        with pytest.raises(WorkspaceBackendError, match="not found"):
            backend.get_session("nonexistent")

    def test_delete_session(self):
        backend = self._make_backend()
        session = backend.create_session()
        assert backend.delete_session(session.id) is True
        assert backend.delete_session(session.id) is False

    def test_abort_session(self):
        backend = self._make_backend()
        session = backend.create_session()
        assert backend.abort_session(session.id) is True
        # Verify status is cancelled
        assert backend._sessions[session.id]["status"] == "cancelled"

    def test_abort_nonexistent(self):
        backend = self._make_backend()
        assert backend.abort_session("nope") is False

    def test_set_risk_tier(self):
        backend = self._make_backend()
        session = backend.create_session()
        backend.set_risk_tier(session.id, 3)
        assert backend._sessions[session.id]["risk_tier"] == 3

    def test_list_agents(self):
        backend = self._make_backend()
        agents = backend.list_agents()
        assert len(agents) == 2
        names = {a.id for a in agents}
        assert "agent-sdk-opus" in names
        assert "agent-sdk-sonnet" in names

    def test_default_risk_tier_from_config(self):
        backend = self._make_backend(default_risk_tier=2)
        session = backend.create_session()
        assert backend._sessions[session.id]["risk_tier"] == 2


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


class TestAgentSDKHealth:
    def test_healthy_with_sdk_and_key(self):
        backend = AgentSDKBackend(AgentSDKConfig())
        # Mock SDK available + API key present
        backend._sdk_available = True
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}):
            assert backend.is_healthy() is True
            health = backend.health()
            assert health.healthy is True

    def test_unhealthy_without_sdk(self):
        backend = AgentSDKBackend(AgentSDKConfig())
        backend._sdk_available = False
        assert backend.is_healthy() is False
        health = backend.health()
        assert health.healthy is False
        assert "not installed" in health.extra.get("error", "")

    def test_unhealthy_without_api_key(self):
        backend = AgentSDKBackend(AgentSDKConfig())
        backend._sdk_available = True
        with patch.dict("os.environ", {}, clear=True):
            assert backend.is_healthy() is False
            health = backend.health()
            assert health.healthy is False
            assert "ANTHROPIC_API_KEY" in health.extra.get("error", "")


# ---------------------------------------------------------------------------
# Query execution (mocked SDK)
# ---------------------------------------------------------------------------


class TestAgentSDKQuery:
    def _make_backend_with_callback(self):
        events = []

        def callback(work_item_id, event_type, payload):
            events.append((work_item_id, event_type, payload))

        config = AgentSDKConfig(working_dir="/tmp/test")
        backend = AgentSDKBackend(config, event_callback=callback)
        return backend, events

    @pytest.mark.asyncio
    async def test_execute_query_success(self):
        backend, events = self._make_backend_with_callback()

        # Mock the SDK module
        mock_result_msg = MagicMock()
        mock_result_msg.result = "Task completed successfully"
        mock_result_msg.session_id = "sdk-session-123"
        mock_result_msg.total_cost_usd = 0.05
        mock_result_msg.num_turns = 3
        mock_result_msg.duration_ms = 5000
        mock_result_msg.is_error = False

        async def mock_query(**kwargs):
            yield mock_result_msg

        mock_sdk = MagicMock()
        mock_sdk.query = mock_query
        mock_sdk.ClaudeAgentOptions = MagicMock()

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            result = await backend._execute_query(
                prompt="Fix the bug",
                risk_tier=1,
                model="claude-sonnet-4-6",
                resume_session_id=None,
                cairn_session_id="test-session",
            )

        assert result["text"] == "Task completed successfully"
        assert result["sdk_session_id"] == "sdk-session-123"
        assert result["cost_usd"] == 0.05
        assert result["is_error"] is False

    @pytest.mark.asyncio
    async def test_execute_query_error(self):
        backend, events = self._make_backend_with_callback()

        async def mock_query(**kwargs):
            raise RuntimeError("API rate limited")
            yield  # make it an async generator  # noqa: E501

        mock_sdk = MagicMock()
        mock_sdk.query = mock_query
        mock_sdk.ClaudeAgentOptions = MagicMock()

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            result = await backend._execute_query(
                prompt="Fix the bug",
                risk_tier=1,
                model=None,
                resume_session_id=None,
                cairn_session_id="test-session",
            )

        assert result["is_error"] is True
        assert "rate limited" in result["text"]

    @pytest.mark.asyncio
    async def test_execute_query_emits_completion_event(self):
        backend, events = self._make_backend_with_callback()

        # Create a session with work_item_id
        session = backend.create_session()
        backend._sessions[session.id]["work_item_id"] = "42"

        mock_result_msg = MagicMock()
        mock_result_msg.result = "Done"
        mock_result_msg.session_id = "sdk-abc"
        mock_result_msg.total_cost_usd = 0.01
        mock_result_msg.num_turns = 1
        mock_result_msg.duration_ms = 1000
        mock_result_msg.is_error = False

        async def mock_query(**kwargs):
            yield mock_result_msg

        mock_sdk = MagicMock()
        mock_sdk.query = mock_query
        mock_sdk.ClaudeAgentOptions = MagicMock()

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            await backend._execute_query(
                prompt="Do it",
                risk_tier=1,
                model=None,
                resume_session_id=None,
                cairn_session_id=session.id,
            )

        # Should have emitted agent.completed event
        completion_events = [e for e in events if e[1] == "agent.completed"]
        assert len(completion_events) == 1
        assert completion_events[0][0] == "42"
        assert completion_events[0][2]["cost_usd"] == 0.01

    @pytest.mark.asyncio
    async def test_execute_query_sdk_not_installed(self):
        backend = AgentSDKBackend(AgentSDKConfig())

        with patch.dict("sys.modules", {"claude_agent_sdk": None}):
            with pytest.raises(WorkspaceBackendError, match="not installed"):
                await backend._execute_query(
                    prompt="test", risk_tier=1, model=None,
                    resume_session_id=None, cairn_session_id="s1",
                )

    def test_send_message_session_not_found(self):
        backend = AgentSDKBackend(AgentSDKConfig())
        with pytest.raises(WorkspaceBackendError, match="not found"):
            backend.send_message("nonexistent", "hello")


# ---------------------------------------------------------------------------
# send_message integration (sync wrapper around async)
# ---------------------------------------------------------------------------


class TestSendMessage:
    def test_send_message_updates_session_state(self):
        backend = AgentSDKBackend(AgentSDKConfig())
        session = backend.create_session(title="test")

        mock_result_msg = MagicMock()
        mock_result_msg.result = "All done"
        mock_result_msg.session_id = "sdk-xyz"
        mock_result_msg.total_cost_usd = 0.02
        mock_result_msg.num_turns = 2
        mock_result_msg.duration_ms = 3000
        mock_result_msg.is_error = False

        async def mock_query(**kwargs):
            yield mock_result_msg

        mock_sdk = MagicMock()
        mock_sdk.query = mock_query
        mock_sdk.ClaudeAgentOptions = MagicMock()

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            msg = backend.send_message(session.id, "Do stuff", risk_tier=2)

        assert msg.parts[0]["text"] == "All done"
        assert msg.extra["sdk_session_id"] == "sdk-xyz"
        assert msg.cost_usd == 0.02

        meta = backend._sessions[session.id]
        assert meta["status"] == "completed"
        assert meta["sdk_session_id"] == "sdk-xyz"
        assert meta["cost_usd"] == 0.02
