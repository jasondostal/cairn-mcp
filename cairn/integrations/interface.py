"""Workspace backend interface ABC. Implementations must provide session + messaging."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorkspaceBackendError(Exception):
    """Raised when a workspace backend operation fails."""

    def __init__(self, message: str, *, backend: str = "", status: int | None = None, body: Any = None):
        super().__init__(message)
        self.backend = backend
        self.status = status
        self.body = body


# ---------------------------------------------------------------------------
# Shared data types
# ---------------------------------------------------------------------------


@dataclass
class AgentSession:
    """A session on a workspace backend."""
    id: str
    title: str | None = None
    parent_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMessage:
    """A message returned from a workspace backend."""
    id: str
    role: str  # "user" | "assistant"
    parts: list[dict[str, Any]] = field(default_factory=list)
    created_at: str | None = None
    session_id: str | None = None
    cost_usd: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentInfo:
    """An agent available on a workspace backend."""
    id: str
    name: str | None = None
    description: str | None = None
    model: str | None = None
    backend: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BackendHealth:
    """Health status from a workspace backend."""
    healthy: bool
    version: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------


class WorkspaceBackend(ABC):
    """Abstract base for workspace agent backends.

    Core methods (abstract — must implement):
        backend_name, is_healthy, health, create_session,
        send_message, send_message_async

    Optional methods (have default no-op/raise implementations):
        get_session, delete_session, abort_session, fork_session,
        get_messages, get_diff, list_agents

    Capability queries (override to advertise support):
        supports_fork, supports_diff, supports_abort, supports_agents
    """

    # -- Core (abstract) -----------------------------------------------------

    @abstractmethod
    def backend_name(self) -> str:
        """Return the backend identifier (e.g. 'opencode', 'claude_code')."""

    @abstractmethod
    def is_healthy(self) -> bool:
        """Quick liveness check — returns False on any error."""

    @abstractmethod
    def health(self) -> BackendHealth:
        """Detailed health check."""

    @abstractmethod
    def create_session(self, *, title: str | None = None, parent_id: str | None = None) -> AgentSession:
        """Create a new session on the backend."""

    @abstractmethod
    def send_message(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        **kwargs: Any,
    ) -> AgentMessage:
        """Send a message and wait for the response."""

    @abstractmethod
    def send_message_async(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Send a message without waiting for a response (fire-and-forget)."""

    # -- Optional (default implementations) ----------------------------------

    def get_session(self, session_id: str) -> AgentSession:
        """Fetch a session by ID. Default: raises NotImplementedError."""
        raise WorkspaceBackendError(
            f"{self.backend_name()} does not support get_session",
            backend=self.backend_name(),
        )

    def delete_session(self, session_id: str) -> bool:
        """Delete a session. Default: raises WorkspaceBackendError."""
        raise WorkspaceBackendError(
            f"{self.backend_name()} does not support delete_session",
            backend=self.backend_name(),
        )

    def abort_session(self, session_id: str) -> bool:
        """Abort an in-progress session. Default: raises WorkspaceBackendError."""
        raise WorkspaceBackendError(
            f"{self.backend_name()} does not support abort_session",
            backend=self.backend_name(),
        )

    def fork_session(self, session_id: str, *, message_id: str | None = None) -> AgentSession:
        """Fork a session. Default: raises WorkspaceBackendError."""
        raise WorkspaceBackendError(
            f"{self.backend_name()} does not support fork_session",
            backend=self.backend_name(),
        )

    def get_messages(self, session_id: str, *, limit: int | None = None) -> list[AgentMessage]:
        """Get messages for a session. Default: returns empty list."""
        return []

    def get_diff(self, session_id: str) -> list[dict[str, Any]]:
        """Get file diffs for a session. Default: returns empty list."""
        return []

    def list_agents(self) -> list[AgentInfo]:
        """List available agents. Default: returns empty list."""
        return []

    # -- Capability queries --------------------------------------------------

    def supports_fork(self) -> bool:
        """Whether this backend supports session forking."""
        return False

    def supports_diff(self) -> bool:
        """Whether this backend supports file diffs."""
        return False

    def supports_abort(self) -> bool:
        """Whether this backend supports aborting sessions."""
        return False

    def supports_agents(self) -> bool:
        """Whether this backend exposes named agents."""
        return False

    # -- Convenience ---------------------------------------------------------

    def capabilities(self) -> dict[str, bool]:
        """Return a dict of all capability flags."""
        return {
            "fork": self.supports_fork(),
            "diff": self.supports_diff(),
            "abort": self.supports_abort(),
            "agents": self.supports_agents(),
        }
