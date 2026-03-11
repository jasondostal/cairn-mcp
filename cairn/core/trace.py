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


@dataclass
class TraceContext:
    """Trace context propagated through an operation.

    Core fields (trace_id, span_id, parent_span_id, actor, entry_point) are
    set at creation and should not be mutated.  Attribution fields (project,
    tool_name, model) are optional and set by MCP tool handlers so downstream
    layers (analytics, event_bus) can read them as ambient context.
    """

    trace_id: str  # 32-char hex (128-bit)
    span_id: str  # 16-char hex (64-bit)
    parent_span_id: str | None = None
    actor: str = "mcp"  # "mcp" | "rest" | "agent" | "system"
    entry_point: str = ""  # tool name or API endpoint
    # Attribution context — set by tool handlers, read by analytics/event_bus
    project: str | None = None
    tool_name: str | None = None
    model: str | None = None


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
        project=parent.project,
        tool_name=parent.tool_name,
        model=parent.model,
    )
    _trace_ctx.set(ctx)
    return ctx


def current_trace() -> TraceContext | None:
    """Read the current trace context (or None if not in a traced operation)."""
    return _trace_ctx.get()


def set_trace_project(project: str) -> None:
    """Set the project on the current trace context.

    Auto-creates a trace if one doesn't exist (MCP tool handlers call this
    before any middleware has started a trace).
    """
    ctx = _trace_ctx.get()
    if ctx is None:
        ctx = new_trace(actor="mcp")
    ctx.project = project


def set_trace_tool(tool_name: str) -> None:
    """Set the tool_name on the current trace context.

    Auto-creates a trace if one doesn't exist (MCP tool handlers call this
    before any middleware has started a trace).
    """
    ctx = _trace_ctx.get()
    if ctx is None:
        ctx = new_trace(actor="mcp", entry_point=tool_name)
    ctx.tool_name = tool_name


def set_trace_model(model: str) -> None:
    """Set the model on the current trace context (no-op if no trace)."""
    ctx = _trace_ctx.get()
    if ctx is not None:
        ctx.model = model


def clear_trace() -> None:
    """Clear the trace context.  Call after the operation completes."""
    _trace_ctx.set(None)
