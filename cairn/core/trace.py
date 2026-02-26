"""TraceContext — per-operation trace propagation via contextvars.

Every MCP tool call or REST request gets a trace_id (32-char hex) and
span_id (16-char hex).  Child spans share the trace_id but get their own
span_id, linking to parent via parent_span_id.

Uses Python stdlib contextvars — zero external dependencies, per-task
isolation in asyncio, per-thread isolation in sync code.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass

_trace_ctx: ContextVar[TraceContext | None] = ContextVar("_trace_ctx", default=None)


def _hex_id(nbytes: int) -> str:
    """Generate a random hex ID."""
    return os.urandom(nbytes).hex()


@dataclass(frozen=True)
class TraceContext:
    """Immutable trace context propagated through an operation."""

    trace_id: str  # 32-char hex (128-bit)
    span_id: str  # 16-char hex (64-bit)
    parent_span_id: str | None = None
    actor: str = "mcp"  # "mcp" | "rest" | "agent" | "system"
    entry_point: str = ""  # tool name or API endpoint


def new_trace(*, actor: str = "mcp", entry_point: str = "") -> TraceContext:
    """Start a new root trace.  Sets the contextvar and returns the context."""
    ctx = TraceContext(
        trace_id=_hex_id(16),
        span_id=_hex_id(8),
        actor=actor,
        entry_point=entry_point,
    )
    _trace_ctx.set(ctx)
    return ctx


def child_span(*, entry_point: str = "") -> TraceContext:
    """Create a child span under the current trace.

    If no current trace exists, creates a new root trace instead.
    """
    parent = _trace_ctx.get()
    if parent is None:
        return new_trace(entry_point=entry_point)

    ctx = TraceContext(
        trace_id=parent.trace_id,
        span_id=_hex_id(8),
        parent_span_id=parent.span_id,
        actor=parent.actor,
        entry_point=entry_point or parent.entry_point,
    )
    _trace_ctx.set(ctx)
    return ctx


def current_trace() -> TraceContext | None:
    """Read the current trace context (or None if not in a traced operation)."""
    return _trace_ctx.get()


def clear_trace() -> None:
    """Clear the trace context.  Call after the operation completes."""
    _trace_ctx.set(None)
