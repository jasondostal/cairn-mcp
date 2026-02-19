"""OpenCode headless server client.

Typed Python client for the OpenCode REST API (opencode serve).
Wraps session management, message sending, MCP registration, and SSE streaming.

Uses stdlib urllib — no extra dependencies required.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Generator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class OpenCodeError(Exception):
    """Raised when an OpenCode API call fails."""

    def __init__(self, message: str, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class HealthStatus:
    healthy: bool
    version: str


@dataclass
class Session:
    id: str
    title: str | None = None
    parent_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TextPart:
    type: str  # "text"
    text: str


@dataclass
class ToolUsePart:
    type: str  # "tool-invocation" / "tool-result"
    tool_name: str | None = None
    args: dict[str, Any] | None = None
    result: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageInfo:
    id: str
    role: str  # "user" | "assistant"
    session_id: str | None = None
    created_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageEnvelope:
    """A message with its info + parts as returned by OpenCode."""
    info: MessageInfo
    parts: list[dict[str, Any]]  # raw part dicts — callers inspect type


@dataclass
class Agent:
    id: str
    name: str | None = None
    description: str | None = None
    model: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SSEvent:
    """Server-Sent Event."""
    event: str | None = None
    data: str = ""
    id: str | None = None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OpenCodeClient:
    """Synchronous REST client for OpenCode headless server.

    Args:
        url: Base URL of the OpenCode server (e.g. ``http://localhost:8080``).
        password: Server password (set via ``OPENCODE_SERVER_PASSWORD``).
        timeout: Request timeout in seconds.
    """

    def __init__(self, url: str, password: str = "", timeout: int = 120):
        self.base_url = url.rstrip("/")
        self.password = password
        self.timeout = timeout
        self._auth_header = self._make_auth_header(password)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _make_auth_header(password: str) -> str | None:
        if not password:
            return None
        creds = base64.b64encode(f"opencode:{password}".encode()).decode()
        return f"Basic {creds}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        query: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> Any:
        """Issue an HTTP request and return parsed JSON (or None for 204)."""
        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)

        data = None
        if body is not None:
            data = json.dumps(body).encode()

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if self._auth_header:
            req.add_header("Authorization", self._auth_header)

        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                if resp.status == 204:
                    return None
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            err_body = None
            try:
                err_body = json.loads(exc.read())
            except Exception:
                pass
            raise OpenCodeError(
                f"OpenCode {method} {path} returned {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise OpenCodeError(f"OpenCode connection failed: {exc}") from exc

    def _get(self, path: str, **kwargs: Any) -> Any:
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, body: dict | None = None, **kwargs: Any) -> Any:
        return self._request("POST", path, body=body, **kwargs)

    def _patch(self, path: str, body: dict | None = None, **kwargs: Any) -> Any:
        return self._request("PATCH", path, body=body, **kwargs)

    def _delete(self, path: str, **kwargs: Any) -> Any:
        return self._request("DELETE", path, **kwargs)

    # -- health --------------------------------------------------------------

    def health(self) -> HealthStatus:
        """Check server health.  ``GET /global/health``"""
        data = self._get("/global/health")
        return HealthStatus(healthy=data["healthy"], version=data.get("version", ""))

    def is_healthy(self) -> bool:
        """Quick liveness check — returns False on any error."""
        try:
            return self.health().healthy
        except Exception:
            return False

    # -- sessions ------------------------------------------------------------

    def list_sessions(self) -> list[Session]:
        """List all sessions.  ``GET /session``"""
        data = self._get("/session")
        return [self._parse_session(s) for s in (data or [])]

    def create_session(
        self, *, title: str | None = None, parent_id: str | None = None
    ) -> Session:
        """Create a new session.  ``POST /session``"""
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if parent_id is not None:
            body["parentID"] = parent_id
        data = self._post("/session", body=body)
        return self._parse_session(data)

    def get_session(self, session_id: str) -> Session:
        """Fetch a session by ID.  ``GET /session/{id}``"""
        data = self._get(f"/session/{session_id}")
        return self._parse_session(data)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session.  ``DELETE /session/{id}``"""
        return bool(self._delete(f"/session/{session_id}"))

    def abort_session(self, session_id: str) -> bool:
        """Abort an in-progress session.  ``POST /session/{id}/abort``"""
        return bool(self._post(f"/session/{session_id}/abort"))

    def fork_session(
        self, session_id: str, *, message_id: str | None = None
    ) -> Session:
        """Fork a session.  ``POST /session/{id}/fork``"""
        body: dict[str, Any] = {}
        if message_id:
            body["messageID"] = message_id
        data = self._post(f"/session/{session_id}/fork", body=body)
        return self._parse_session(data)

    def get_diff(
        self, session_id: str, *, message_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get file diffs for a session.  ``GET /session/{id}/diff``"""
        query = {}
        if message_id:
            query["messageID"] = message_id
        return self._get(f"/session/{session_id}/diff", query=query or None) or []

    def get_session_status(self) -> dict[str, Any]:
        """Get status of all sessions.  ``GET /session/status``"""
        return self._get("/session/status") or {}

    # -- messages ------------------------------------------------------------

    def send_message(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        model: str | None = None,
        system: str | None = None,
        no_reply: bool = False,
    ) -> MessageEnvelope:
        """Send a message and wait for the response.  ``POST /session/{id}/message``

        Args:
            session_id: Target session.
            text: User message text.
            agent: Agent to use (e.g. ``"cairn-build"``).
            model: Override model for this message.
            system: Override system prompt.
            no_reply: If True, the agent won't respond (message-only).

        Returns:
            The assistant's response message with parts.
        """
        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": text}],
        }
        if agent:
            body["agent"] = agent
        if model:
            body["model"] = model
        if system:
            body["system"] = system
        if no_reply:
            body["noReply"] = True

        data = self._post(
            f"/session/{session_id}/message",
            body=body,
            timeout=max(self.timeout, 300),  # agent responses can be slow
        )
        return self._parse_message_envelope(data)

    def send_message_async(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> None:
        """Send a message asynchronously (fire-and-forget).  ``POST /session/{id}/prompt_async``

        Use :meth:`subscribe_events` or :meth:`get_messages` to get the response.
        """
        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": text}],
        }
        if agent:
            body["agent"] = agent
        if model:
            body["model"] = model
        if system:
            body["system"] = system

        self._post(f"/session/{session_id}/prompt_async", body=body)

    def get_messages(
        self, session_id: str, *, limit: int | None = None
    ) -> list[MessageEnvelope]:
        """Get messages for a session.  ``GET /session/{id}/message``"""
        query = {}
        if limit is not None:
            query["limit"] = str(limit)
        data = self._get(f"/session/{session_id}/message", query=query or None)
        return [self._parse_message_envelope(m) for m in (data or [])]

    def get_message(self, session_id: str, message_id: str) -> MessageEnvelope:
        """Get a single message.  ``GET /session/{id}/message/{messageID}``"""
        data = self._get(f"/session/{session_id}/message/{message_id}")
        return self._parse_message_envelope(data)

    # -- agents --------------------------------------------------------------

    def list_agents(self) -> list[Agent]:
        """List available agents.  ``GET /agent``"""
        data = self._get("/agent")
        return [self._parse_agent(a) for a in (data or [])]

    # -- MCP servers ---------------------------------------------------------

    def get_mcp_status(self) -> dict[str, Any]:
        """Get status of all registered MCP servers.  ``GET /mcp``"""
        return self._get("/mcp") or {}

    def register_mcp(
        self,
        name: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Register a remote MCP server.  ``POST /mcp``

        Args:
            name: Name for the MCP server (e.g. ``"cairn"``).
            url: HTTP URL of the MCP server.
            headers: Optional HTTP headers for auth.
            enabled: Whether the server is enabled.
        """
        body = {
            "name": name,
            "config": {
                "type": "remote",
                "url": url,
                "headers": headers or {},
                "enabled": enabled,
            },
        }
        return self._post("/mcp", body=body) or {}

    # -- files ---------------------------------------------------------------

    def get_file_content(self, path: str) -> dict[str, Any]:
        """Read a file from the worker.  ``GET /file/content``"""
        return self._get("/file/content", query={"path": path}) or {}

    def get_file_status(self) -> list[dict[str, Any]]:
        """Get git status of files.  ``GET /file/status``"""
        return self._get("/file/status") or []

    def find_files(self, query: str, *, limit: int | None = None) -> list[str]:
        """Find files by name.  ``GET /find/file``"""
        q: dict[str, str] = {"query": query}
        if limit is not None:
            q["limit"] = str(limit)
        return self._get("/find/file", query=q) or []

    # -- SSE events ----------------------------------------------------------

    def subscribe_events(self, *, timeout: int = 0) -> Generator[SSEvent, None, None]:
        """Stream SSE events from the server.  ``GET /event``

        Yields :class:`SSEvent` objects. Set ``timeout=0`` for indefinite streaming.

        Use this to monitor agent progress after :meth:`send_message_async`.
        """
        url = f"{self.base_url}/event"
        req = urllib.request.Request(url)
        req.add_header("Accept", "text/event-stream")
        if self._auth_header:
            req.add_header("Authorization", self._auth_header)

        resp = urllib.request.urlopen(req, timeout=timeout or None)
        try:
            event = SSEvent()
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

                if not line:
                    # Blank line = dispatch event
                    if event.data:
                        yield event
                    event = SSEvent()
                    continue

                if line.startswith("event:"):
                    event.event = line[6:].strip()
                elif line.startswith("data:"):
                    event.data += line[5:].strip()
                elif line.startswith("id:"):
                    event.id = line[3:].strip()
                # ignore other fields (retry:, comments)
        finally:
            resp.close()

    # -- config & providers --------------------------------------------------

    def get_config(self) -> dict[str, Any]:
        """Get server configuration.  ``GET /config``"""
        return self._get("/config") or {}

    def get_providers(self) -> dict[str, Any]:
        """Get available providers.  ``GET /config/providers``"""
        return self._get("/config/providers") or {}

    # -- parsers -------------------------------------------------------------

    @staticmethod
    def _parse_session(data: dict[str, Any]) -> Session:
        return Session(
            id=data["id"],
            title=data.get("title"),
            parent_id=data.get("parentID"),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            extra={k: v for k, v in data.items()
                   if k not in ("id", "title", "parentID", "createdAt", "updatedAt")},
        )

    @staticmethod
    def _parse_message_envelope(data: dict[str, Any]) -> MessageEnvelope:
        info_raw = data.get("info", {})
        return MessageEnvelope(
            info=MessageInfo(
                id=info_raw.get("id", ""),
                role=info_raw.get("role", ""),
                session_id=info_raw.get("sessionID"),
                created_at=info_raw.get("createdAt"),
                extra={k: v for k, v in info_raw.items()
                       if k not in ("id", "role", "sessionID", "createdAt")},
            ),
            parts=data.get("parts", []),
        )

    @staticmethod
    def _parse_agent(data: dict[str, Any]) -> Agent:
        # OpenCode uses "name" as the agent identifier
        name = data.get("name", "")
        model_info = data.get("model")
        model_str = None
        if isinstance(model_info, dict):
            model_str = f"{model_info.get('providerID', '')}/{model_info.get('modelID', '')}"
        elif isinstance(model_info, str):
            model_str = model_info
        return Agent(
            id=name,
            name=name,
            description=data.get("description"),
            model=model_str,
            extra={k: v for k, v in data.items()
                   if k not in ("name", "description", "model")},
        )

    # -- convenience ---------------------------------------------------------

    def send_and_collect_text(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> str:
        """Send a message and return the assistant's text response as a string.

        Concatenates all ``TextPart`` content from the response. Useful when
        you just want the final text answer.
        """
        envelope = self.send_message(
            session_id, text, agent=agent, model=model, system=system
        )
        parts = []
        for part in envelope.parts:
            if part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "\n".join(parts)

    def wait_for_completion(
        self,
        session_id: str,
        *,
        poll_interval: float = 2.0,
        max_wait: float = 600.0,
    ) -> list[MessageEnvelope]:
        """Poll until the session is no longer busy, then return all messages.

        Useful after :meth:`send_message_async` to wait for the agent to finish.
        """
        start = time.monotonic()
        while time.monotonic() - start < max_wait:
            statuses = self.get_session_status()
            session_status = statuses.get(session_id, {})
            if not session_status.get("busy", False):
                break
            time.sleep(poll_interval)
        return self.get_messages(session_id)


# ---------------------------------------------------------------------------
# WorkspaceBackend adapter
# ---------------------------------------------------------------------------


from cairn.integrations.interface import (  # noqa: E402
    AgentInfo,
    AgentMessage,
    AgentSession,
    BackendHealth,
    WorkspaceBackend,
    WorkspaceBackendError,
)


class OpenCodeBackend(WorkspaceBackend):
    """Adapts :class:`OpenCodeClient` to the :class:`WorkspaceBackend` ABC.

    Thin wrapper — delegates every operation to the underlying client and
    translates OpenCode data types to the shared backend types.
    """

    def __init__(self, client: OpenCodeClient):
        self._client = client

    # -- Core ----------------------------------------------------------------

    def backend_name(self) -> str:
        return "opencode"

    def is_healthy(self) -> bool:
        return self._client.is_healthy()

    def health(self) -> BackendHealth:
        try:
            h = self._client.health()
            return BackendHealth(healthy=h.healthy, version=h.version)
        except OpenCodeError as exc:
            return BackendHealth(healthy=False, extra={"error": str(exc)})

    def create_session(self, *, title: str | None = None, parent_id: str | None = None) -> AgentSession:
        try:
            s = self._client.create_session(title=title, parent_id=parent_id)
            return self._to_agent_session(s)
        except OpenCodeError as exc:
            raise WorkspaceBackendError(str(exc), backend="opencode", status=exc.status) from exc

    def send_message(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        **kwargs: Any,
    ) -> AgentMessage:
        try:
            env = self._client.send_message(session_id, text, agent=agent)
            return AgentMessage(
                id=env.info.id,
                role=env.info.role,
                parts=env.parts,
                created_at=env.info.created_at,
                session_id=env.info.session_id,
            )
        except OpenCodeError as exc:
            raise WorkspaceBackendError(str(exc), backend="opencode", status=exc.status) from exc

    def send_message_async(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        **kwargs: Any,
    ) -> None:
        try:
            self._client.send_message_async(session_id, text, agent=agent)
        except OpenCodeError as exc:
            raise WorkspaceBackendError(str(exc), backend="opencode", status=exc.status) from exc

    # -- Optional (all supported) --------------------------------------------

    def get_session(self, session_id: str) -> AgentSession:
        try:
            s = self._client.get_session(session_id)
            return self._to_agent_session(s)
        except OpenCodeError as exc:
            raise WorkspaceBackendError(str(exc), backend="opencode", status=exc.status) from exc

    def delete_session(self, session_id: str) -> bool:
        try:
            return self._client.delete_session(session_id)
        except OpenCodeError as exc:
            raise WorkspaceBackendError(str(exc), backend="opencode", status=exc.status) from exc

    def abort_session(self, session_id: str) -> bool:
        try:
            return self._client.abort_session(session_id)
        except OpenCodeError as exc:
            raise WorkspaceBackendError(str(exc), backend="opencode", status=exc.status) from exc

    def fork_session(self, session_id: str, *, message_id: str | None = None) -> AgentSession:
        try:
            s = self._client.fork_session(session_id, message_id=message_id)
            return self._to_agent_session(s)
        except OpenCodeError as exc:
            raise WorkspaceBackendError(str(exc), backend="opencode", status=exc.status) from exc

    def get_messages(self, session_id: str, *, limit: int | None = None) -> list[AgentMessage]:
        try:
            envelopes = self._client.get_messages(session_id, limit=limit)
            return [
                AgentMessage(
                    id=env.info.id,
                    role=env.info.role,
                    parts=env.parts,
                    created_at=env.info.created_at,
                    session_id=env.info.session_id,
                )
                for env in envelopes
            ]
        except OpenCodeError as exc:
            raise WorkspaceBackendError(str(exc), backend="opencode", status=exc.status) from exc

    def get_diff(self, session_id: str) -> list[dict[str, Any]]:
        try:
            return self._client.get_diff(session_id)
        except OpenCodeError as exc:
            raise WorkspaceBackendError(str(exc), backend="opencode", status=exc.status) from exc

    def list_agents(self) -> list[AgentInfo]:
        try:
            agents = self._client.list_agents()
            return [
                AgentInfo(
                    id=a.id,
                    name=a.name,
                    description=a.description,
                    model=a.model,
                    backend="opencode",
                )
                for a in agents
            ]
        except OpenCodeError as exc:
            raise WorkspaceBackendError(str(exc), backend="opencode", status=exc.status) from exc

    # -- Capabilities --------------------------------------------------------

    def supports_fork(self) -> bool:
        return True

    def supports_diff(self) -> bool:
        return True

    def supports_abort(self) -> bool:
        return True

    def supports_agents(self) -> bool:
        return True

    # -- Internal ------------------------------------------------------------

    @staticmethod
    def _to_agent_session(s: Session) -> AgentSession:
        return AgentSession(
            id=s.id,
            title=s.title,
            parent_id=s.parent_id,
            created_at=s.created_at,
            updated_at=s.updated_at,
            extra=s.extra,
        )
