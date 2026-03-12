"""CairnEvent — unified event schema for the event bus.

Every event in cairn flows through one shape. Domain mutations, tool calls,
LLM/embedding usage, external hooks — all represented as CairnEvent instances.
All events persist to Postgres and trigger NOTIFY for real-time SSE streaming.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class CairnEvent:
    """Single event shape for the entire cairn event bus.

    Fields follow the WHO/DID/WHAT/WHEN/WHERE pattern:
    - WHO: actor, session_name, agent_id
    - DID: event_type (domain.verb)
    - WHAT: tool_name, work_item_id, payload
    - WHEN: created_at
    - WHERE: project
    """

    # What happened — "domain.verb" e.g. memory.created, tool.search, llm.generated
    event_type: str

    # Who — session context (system events use "__system__")
    session_name: str = "__system__"

    # Who — actor type
    actor: str = "system"  # "mcp" | "rest" | "agent" | "system" | "hook"

    # Where — project scope
    project: str | None = None

    # Who — agent identity (for dispatched/orchestrated work)
    agent_id: str | None = None

    # What — work item association
    work_item_id: int | None = None

    # What — tool that produced this event
    tool_name: str | None = None

    # Tracing
    trace_id: str | None = None
    span_id: str | None = None

    # What — arbitrary event data (tokens, latency, IDs, etc.)
    payload: dict = field(default_factory=dict)

    # When
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        """Convert to a plain dict for dispatch and observer consumption."""
        return {
            "event_type": self.event_type,
            "tool_name": self.tool_name,
            "project": self.project,
            "session_name": self.session_name,
            "actor": self.actor,
            "payload": self.payload,
        }
