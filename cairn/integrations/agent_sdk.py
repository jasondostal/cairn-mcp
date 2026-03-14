"""Claude Agent SDK backend — uses ``claude-agent-sdk`` pip package.

Unlike the Claude Code CLI backend which spawns ``claude -p`` subprocesses,
this backend uses the Agent SDK's ``query()`` function for native Python
integration with streaming, hooks, MCP support, and session management.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from cairn.integrations.interface import (
    AgentInfo,
    AgentMessage,
    AgentSession,
    BackendHealth,
    WorkspaceBackend,
    WorkspaceBackendError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class AgentSDKConfig:
    """Configuration for the Agent SDK backend."""
    working_dir: str = ""                   # cwd for agent execution
    max_turns: int = 50                     # max agentic turns per query
    max_budget_usd: float = 5.0             # spending cap per dispatch (0 = no limit)
    cairn_mcp_url: str = ""                 # Cairn MCP URL for self-service context
    default_model: str = ""                 # default model (empty = SDK default)
    sandbox_enabled: bool = True            # enable SDK sandboxing
    default_risk_tier: int = 1              # default risk tier for new sessions


# ---------------------------------------------------------------------------
# Risk tier → SDK permission + tool mapping
# ---------------------------------------------------------------------------

# Tier 0: research-only (read, search, no modifications)
# Tier 1: guided autonomy (edits auto-approved, bash needs approval)
# Tier 2: broad autonomy (edits + bash auto-approved)
# Tier 3: full autonomy (all tools, bypass permissions — gated work items only)

_TIER_TOOLS: dict[int, list[str]] = {
    0: ["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
    1: ["Read", "Glob", "Grep", "Edit", "Write", "WebSearch", "WebFetch"],
    2: ["Read", "Glob", "Grep", "Edit", "Write", "Bash", "WebSearch", "WebFetch", "Agent"],
    3: ["Read", "Glob", "Grep", "Edit", "Write", "Bash", "WebSearch", "WebFetch", "Agent"],
}

_TIER_PERMISSION_MODE: dict[int, str] = {
    0: "plan",               # read-only analysis
    1: "acceptEdits",        # auto-approve file edits
    2: "acceptEdits",        # auto-approve edits, bash via allowed_tools
    3: "bypassPermissions",  # full autonomy
}


def _cairn_mcp_tools(tier: int) -> list[str]:
    """MCP tool allowlist for Cairn self-service, scoped by risk tier."""
    base = [
        "mcp__cairn__orient",
        "mcp__cairn__search",
        "mcp__cairn__recall",
        "mcp__cairn__rules",
    ]
    if tier >= 1:
        base.extend([
            "mcp__cairn__store",
            "mcp__cairn__work_items",
        ])
    return base


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class AgentSDKBackend(WorkspaceBackend):
    """Workspace backend using the Claude Agent SDK (pip package).

    Uses ``claude_agent_sdk.query()`` for native async agent execution
    with streaming, hooks, and MCP support.
    """

    def __init__(
        self,
        config: AgentSDKConfig | None = None,
        *,
        event_callback: Callable[[str, str, dict[str, Any]], None] | None = None,
    ):
        self._config = config or AgentSDKConfig()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        # Optional callback: event_callback(work_item_id, event_type, payload)
        self._event_callback = event_callback
        self._sdk_available: bool | None = None

    def _check_sdk(self) -> bool:
        """Check if claude-agent-sdk is installed."""
        if self._sdk_available is None:
            try:
                import claude_agent_sdk  # noqa: F401
                self._sdk_available = True
            except ImportError:
                self._sdk_available = False
        return self._sdk_available

    # -- Core ----------------------------------------------------------------

    def backend_name(self) -> str:
        return "agent_sdk"

    def is_healthy(self) -> bool:
        if not self._check_sdk():
            return False
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        return bool(api_key)

    def health(self) -> BackendHealth:
        if not self._check_sdk():
            return BackendHealth(healthy=False, extra={
                "error": "claude-agent-sdk not installed (pip install claude-agent-sdk)",
            })
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return BackendHealth(healthy=False, extra={
                "error": "ANTHROPIC_API_KEY not set",
            })
        try:
            import claude_agent_sdk
            version = getattr(claude_agent_sdk, "__version__", "unknown")
        except Exception:
            version = "unknown"
        return BackendHealth(
            healthy=True,
            version=version,
            extra={
                "sandbox": self._config.sandbox_enabled,
                "working_dir": self._config.working_dir or "(cwd)",
                "default_model": self._config.default_model or "(sdk default)",
            },
        )

    def create_session(self, *, title: str | None = None, parent_id: str | None = None) -> AgentSession:
        session_id = f"sdk-{int(time.time() * 1000)}"
        session = AgentSession(
            id=session_id,
            title=title,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        with self._lock:
            self._sessions[session_id] = {
                "session": session,
                "sdk_session_id": None,   # captured from SDK ResultMessage
                "risk_tier": self._config.default_risk_tier,
                "model": None,
                "cost_usd": None,
                "num_turns": None,
                "status": "created",      # created → running → completed → error
                "work_item_id": None,
            }
        return session

    def send_message(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        risk_tier: int | None = None,
        model: str | None = None,
        work_item_id: str | None = None,
        **kwargs: Any,
    ) -> AgentMessage:
        """Send a message synchronously via Agent SDK query()."""
        with self._lock:
            meta = self._sessions.get(session_id)
        if not meta:
            raise WorkspaceBackendError(f"Session {session_id} not found", backend="agent_sdk")

        tier = risk_tier if risk_tier is not None else meta.get("risk_tier", self._config.default_risk_tier)
        resolved_model = model or meta.get("model") or self._config.default_model or None
        sdk_sid = meta.get("sdk_session_id")

        if work_item_id:
            with self._lock:
                meta["work_item_id"] = work_item_id

        if resolved_model and not meta.get("model"):
            with self._lock:
                meta["model"] = resolved_model

        auth_token = kwargs.get("auth_token") or ""

        # Run the async query in a thread-safe way
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an existing event loop — run in a new thread
                result = self._run_in_thread(
                    self._execute_query, text, tier, resolved_model, sdk_sid, session_id, auth_token,
                )
            else:
                result = loop.run_until_complete(
                    self._execute_query(text, tier, resolved_model, sdk_sid, session_id, auth_token),
                )
        except RuntimeError:
            # No event loop — create one
            result = asyncio.run(
                self._execute_query(text, tier, resolved_model, sdk_sid, session_id, auth_token),
            )

        # Update session metadata from result
        with self._lock:
            if result.get("sdk_session_id"):
                meta["sdk_session_id"] = result["sdk_session_id"]
            if result.get("cost_usd") is not None:
                meta["cost_usd"] = result["cost_usd"]
            if result.get("num_turns") is not None:
                meta["num_turns"] = result["num_turns"]
            meta["status"] = "completed" if not result.get("is_error") else "error"

        return AgentMessage(
            id=f"msg-{int(time.time() * 1000)}",
            role="assistant",
            parts=[{"type": "text", "text": result.get("text", "")}],
            session_id=session_id,
            cost_usd=result.get("cost_usd"),
            extra={
                "sdk_session_id": result.get("sdk_session_id"),
                "num_turns": result.get("num_turns"),
                "duration_ms": result.get("duration_ms"),
                "model": resolved_model,
            },
        )

    def send_message_async(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        risk_tier: int | None = None,
        model: str | None = None,
        work_item_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Fire-and-forget: runs send_message in a background thread."""
        def _run():
            try:
                with self._lock:
                    meta = self._sessions.get(session_id)
                    if meta:
                        meta["status"] = "running"
                self.send_message(
                    session_id, text, agent=agent,
                    risk_tier=risk_tier, model=model,
                    work_item_id=work_item_id, **kwargs,
                )
            except WorkspaceBackendError:
                logger.warning("Async send_message failed for session %s", session_id, exc_info=True)
                with self._lock:
                    meta = self._sessions.get(session_id)
                    if meta:
                        meta["status"] = "error"

        thread = threading.Thread(target=_run, daemon=True, name=f"agent-sdk-{session_id}")
        thread.start()

    # -- Optional overrides --------------------------------------------------

    def get_session(self, session_id: str) -> AgentSession:
        with self._lock:
            meta = self._sessions.get(session_id)
        if not meta:
            raise WorkspaceBackendError(f"Session {session_id} not found", backend="agent_sdk")
        return meta["session"]

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            removed = self._sessions.pop(session_id, None)
        return removed is not None

    def abort_session(self, session_id: str) -> bool:
        # Agent SDK doesn't expose a cancel mechanism from outside the iterator.
        # Mark as cancelled locally so heartbeat callbacks know to stop.
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta:
                meta["status"] = "cancelled"
                return True
        return False

    def list_agents(self) -> list[AgentInfo]:
        return [
            AgentInfo(
                id="agent-sdk-opus",
                name="Agent SDK (Opus)",
                description="Claude Agent SDK — Opus 4.6",
                model="claude-opus-4-6",
                backend="agent_sdk",
            ),
            AgentInfo(
                id="agent-sdk-sonnet",
                name="Agent SDK (Sonnet)",
                description="Claude Agent SDK — Sonnet 4.6",
                model="claude-sonnet-4-6",
                backend="agent_sdk",
            ),
        ]

    # -- Capabilities --------------------------------------------------------

    def supports_fork(self) -> bool:
        return True  # SDK supports fork_session

    def supports_abort(self) -> bool:
        return True

    def supports_agents(self) -> bool:
        return True

    # -- Internal ------------------------------------------------------------

    def _run_in_thread(self, coro_fn, *args):
        """Run an async function in a new thread with its own event loop."""
        result = {}
        exc_holder = {}

        def _target():
            try:
                result["value"] = asyncio.run(coro_fn(*args))
            except Exception as e:
                exc_holder["error"] = e

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join(timeout=660)  # 11 min — slightly longer than SDK timeout
        if "error" in exc_holder:
            raise WorkspaceBackendError(
                f"Agent SDK query failed: {exc_holder['error']}",
                backend="agent_sdk",
            )
        return result.get("value", {})

    async def _execute_query(
        self,
        prompt: str,
        risk_tier: int,
        model: str | None,
        resume_session_id: str | None,
        cairn_session_id: str,
        auth_token: str = "",
    ) -> dict[str, Any]:
        """Execute an Agent SDK query() and collect the result."""
        try:
            from claude_agent_sdk import query, ClaudeAgentOptions
        except ImportError as e:
            raise WorkspaceBackendError(
                "claude-agent-sdk not installed (pip install claude-agent-sdk)",
                backend="agent_sdk",
            ) from e

        # Build tool list with Cairn MCP tools
        tools = list(_TIER_TOOLS.get(risk_tier, _TIER_TOOLS[1]))
        tools.extend(_cairn_mcp_tools(risk_tier))

        # Build options
        opts_kwargs: dict[str, Any] = {
            "allowed_tools": tools,
            "permission_mode": _TIER_PERMISSION_MODE.get(risk_tier, "acceptEdits"),
        }

        if model:
            opts_kwargs["model"] = model

        if self._config.max_turns > 0:
            opts_kwargs["max_turns"] = self._config.max_turns

        if self._config.max_budget_usd > 0:
            opts_kwargs["max_budget_usd"] = self._config.max_budget_usd

        if self._config.working_dir:
            opts_kwargs["cwd"] = self._config.working_dir

        if resume_session_id:
            opts_kwargs["resume"] = resume_session_id

        # MCP server config for Cairn self-service (inherits dispatching user's identity)
        if self._config.cairn_mcp_url:
            server_cfg: dict[str, Any] = {
                "type": "http",
                "url": self._config.cairn_mcp_url,
            }
            if auth_token:
                server_cfg["headers"] = {
                    "Authorization": f"Bearer {auth_token}",
                }
            opts_kwargs["mcp_servers"] = {"cairn": server_cfg}

        # Sandbox config
        if self._config.sandbox_enabled:
            opts_kwargs["sandbox"] = {
                "enabled": True,
                "autoAllowBashIfSandboxed": True,
            }

        options = ClaudeAgentOptions(**opts_kwargs)

        # Execute query and collect results
        result_text = ""
        sdk_session_id = None
        cost_usd = None
        num_turns = None
        duration_ms = None
        is_error = False

        try:
            async for message in query(prompt=prompt, options=options):
                # Capture session ID from init message
                if hasattr(message, "subtype") and message.subtype == "init":
                    sdk_session_id = getattr(message, "session_id", None)

                # Capture result from final message
                if hasattr(message, "result"):
                    result_text = message.result or ""
                    sdk_session_id = getattr(message, "session_id", sdk_session_id)
                    cost_usd = getattr(message, "total_cost_usd", None)
                    num_turns = getattr(message, "num_turns", None)
                    duration_ms = getattr(message, "duration_ms", None)
                    is_error = getattr(message, "is_error", False)

                # Emit heartbeat on assistant messages (tool activity)
                if hasattr(message, "content") and self._event_callback:
                    with self._lock:
                        meta = self._sessions.get(cairn_session_id, {})
                    wi_id = meta.get("work_item_id")
                    if wi_id:
                        self._event_callback(wi_id, "agent.heartbeat", {
                            "session_id": cairn_session_id,
                            "sdk_session_id": sdk_session_id,
                        })

        except Exception as e:
            logger.error("Agent SDK query failed: %s", e, exc_info=True)
            is_error = True
            result_text = f"Agent SDK error: {e}"

        # Emit completion event
        if self._event_callback:
            with self._lock:
                meta = self._sessions.get(cairn_session_id, {})
            wi_id = meta.get("work_item_id")
            if wi_id:
                self._event_callback(wi_id, "agent.completed", {
                    "session_id": cairn_session_id,
                    "sdk_session_id": sdk_session_id,
                    "cost_usd": cost_usd,
                    "num_turns": num_turns,
                    "is_error": is_error,
                })

        return {
            "text": result_text,
            "sdk_session_id": sdk_session_id,
            "cost_usd": cost_usd,
            "num_turns": num_turns,
            "duration_ms": duration_ms,
            "is_error": is_error,
        }

    def set_risk_tier(self, session_id: str, risk_tier: int) -> None:
        """Update the risk tier for an existing session."""
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta:
                meta["risk_tier"] = risk_tier
