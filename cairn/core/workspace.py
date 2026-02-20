"""Workspace manager: bridge between Cairn context and agent backends.

Assembles context from Cairn (rules, memories, project docs, cairn trail)
and manages workspace sessions across multiple backends (OpenCode, Claude Code).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from cairn.core.analytics import track_operation
from cairn.core.budget import estimate_tokens, truncate_to_budget
from cairn.core.constants import (
    WORKSPACE_ALLOC_MEMORIES, WORKSPACE_ALLOC_RULES,
    WORKSPACE_ALLOC_TASKS, WORKSPACE_ALLOC_TRAIL,
)

from cairn.core.utils import get_or_create_project, get_project
from cairn.core.work_items import WorkItemManager
from cairn.integrations.interface import WorkspaceBackend, WorkspaceBackendError
from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Manages workspace sessions bridging Cairn memory and agent backends.

    Responsibilities:
    - Assemble context from Cairn (rules, recent memories, project docs, trail)
    - Create sessions on any registered backend with injected context
    - Track session→project→backend mapping for lifecycle management
    """

    def __init__(
        self,
        db: Database,
        backends: dict[str, WorkspaceBackend] | None = None,
        *,
        default_backend: str = "opencode",
        work_item_manager: WorkItemManager | None = None,
        default_agent: str = "cairn-build",
        budget_tokens: int = 6000,
    ):
        self.db = db
        self._backends = backends or {}
        self._default_backend = default_backend
        self.work_item_manager = work_item_manager
        self.default_agent = default_agent
        self.budget_tokens = budget_tokens

    # -- backend resolution --------------------------------------------------

    def _get_backend(self, name: str | None = None) -> WorkspaceBackend:
        """Resolve a backend by name, falling back to the default.

        Raises WorkspaceBackendError if the requested backend is not available.
        """
        backend_name = name or self._default_backend
        backend = self._backends.get(backend_name)
        if not backend:
            available = ", ".join(self._backends) or "none"
            raise WorkspaceBackendError(
                f"Backend '{backend_name}' not configured (available: {available})",
                backend=backend_name,
            )
        return backend

    def _backend_for_session(self, session_id: str) -> WorkspaceBackend:
        """Look up which backend owns a session from the DB record."""
        row = self.db.execute_one(
            "SELECT backend FROM workspace_sessions WHERE backend_session_id = %s",
            (session_id,),
        )
        if not row:
            # Fall back to default if no DB record (e.g. direct OpenCode session)
            return self._get_backend()
        return self._get_backend(row["backend"])

    def _has_any_backend(self) -> bool:
        """Check if at least one backend is configured."""
        return bool(self._backends)

    # -- context assembly ----------------------------------------------------

    @track_operation("workspace.build_context")
    def build_context(
        self,
        project: str,
        *,
        task: str | None = None,
        mode: str = "focused",
    ) -> str:
        """Assemble Cairn context into a prompt for an agent session.

        Modes:
        - ``focused`` (default): Lean context for autonomous task agents.
          Project-specific rules only (no __global__ grimoire), task-relevant
          memories. Skips trail and pending tasks — the agent definition
          handles behavioral instructions.
        - ``full``: Rich context for interactive sessions. Includes global +
          project rules, recent cairn trail, relevant memories, and pending
          tasks. Use when the agent needs the full picture.

        Returns a formatted context string suitable for injection as a system message.
        """
        if mode == "full":
            return self._build_full_context(project, task=task)
        return self._build_focused_context(project, task=task)

    def _build_focused_context(self, project: str, *, task: str | None = None) -> str:
        """Lean context for autonomous task agents.

        Only includes project-specific rules and task-relevant memories.
        The agent definition (e.g. cairn-build.md) handles behavioral instructions.
        """
        sections: list[str] = []

        # Project-specific rules only — no __global__ grimoire
        rules = self._fetch_rules(project, include_global=False)
        if rules:
            sections.append("## Project Rules\n" + "\n".join(
                f"- {r['content'][:200]}" for r in rules
            ))

        # Task-relevant memories (narrower — 3 results)
        if task:
            memories = self._search_memories(project, task, limit=3)
            if memories:
                mem_lines = []
                for m in memories:
                    summary = m.get("summary") or m.get("content", "")[:150]
                    mem_lines.append(f"- [{m.get('memory_type', 'note')}] {summary}")
                sections.append("## Relevant Context\n" + "\n".join(mem_lines))

        if not sections:
            return f"Project: {project}\nNo prior context found."

        header = f"# Cairn Context — {project}\n\n"
        return header + "\n\n".join(sections)

    def _build_full_context(self, project: str, *, task: str | None = None) -> str:
        """Rich context for interactive sessions — full grimoire.

        Budget is allocated across sections by priority:
        - Rules 35%, Memories 30%, Trail 20%, Tasks 15%
        If a section uses less than its allocation, the remainder flows
        to lower-priority sections.
        """
        total_budget = self.budget_tokens
        sections: list[str] = []
        budget_remaining = total_budget

        # Allocate budgets (tokens) per section
        budget_rules = int(total_budget * WORKSPACE_ALLOC_RULES)
        budget_memories = int(total_budget * WORKSPACE_ALLOC_MEMORIES)
        budget_trail = int(total_budget * WORKSPACE_ALLOC_TRAIL)
        budget_tasks = int(total_budget * WORKSPACE_ALLOC_TASKS)

        # Section 1: Rules (highest priority)
        rules = self._fetch_rules(project, include_global=True)
        if rules:
            rules_text = self._format_rules(rules, budget_rules)
            rules_tokens = estimate_tokens(rules_text)
            sections.append(rules_text)
            budget_remaining -= rules_tokens
            # Surplus flows to memories
            surplus = max(0, budget_rules - rules_tokens)
            budget_memories += surplus
        else:
            budget_memories += budget_rules

        # Section 2: Memories
        if task:
            memories = self._search_memories(project, task, limit=5)
            if memories:
                mem_text = self._format_memories(memories, budget_memories)
                mem_tokens = estimate_tokens(mem_text)
                sections.append(mem_text)
                budget_remaining -= mem_tokens
                surplus = max(0, budget_memories - mem_tokens)
                budget_trail += surplus
            else:
                budget_trail += budget_memories
        else:
            budget_trail += budget_memories

        # Section 3: Trail
        trail = self._fetch_trail(project, limit=3)
        if trail:
            trail_text = self._format_trail(trail, budget_trail)
            trail_tokens = estimate_tokens(trail_text)
            sections.append(trail_text)
            budget_remaining -= trail_tokens
            surplus = max(0, budget_trail - trail_tokens)
            budget_tasks += surplus
        else:
            budget_tasks += budget_trail

        # Section 4: Tasks (lowest priority)
        tasks_data = self._fetch_tasks(project)
        if tasks_data:
            tasks_text = self._format_tasks(tasks_data, budget_tasks)
            sections.append(tasks_text)

        if not sections:
            return f"Project: {project}\nNo prior context found."

        header = f"# Cairn Context — {project}\n\n"
        return header + "\n\n".join(sections)

    # -- session management --------------------------------------------------

    @track_operation("workspace.create_session")
    def create_session(
        self,
        project: str,
        *,
        task: str | None = None,
        fork_from: str | None = None,
        title: str | None = None,
        agent: str | None = None,
        inject_context: bool = True,
        context_mode: str = "focused",
        backend: str | None = None,
        risk_tier: int | None = None,
        work_item_id: int | str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Create a workspace session with Cairn context injected.

        Instructions can come from multiple sources:
        - ``task``: Raw text description.
        - ``work_item_id``: Dispatch from a work item (generates structured briefing).
        - ``fork_from``: Fork an existing session (full history carry-over).
        - All can be combined.

        Args:
            project: Cairn project name for context.
            task: Optional task description.
            work_item_id: Optional work item ID — generates a dispatch briefing.
            fork_from: Optional session ID to fork from.
            title: Session title (auto-generated if omitted).
            agent: Agent to use (defaults to workspace default).
            inject_context: Whether to inject Cairn context as first message.
            context_mode: "focused" (default, lean) or "full" (grimoire + trail).
            backend: Backend to use (defaults to config default).
            risk_tier: Risk tier for permission scoping (Claude Code only).
            model: Model override for Claude Code (e.g. "claude-sonnet-4-6").

        Returns:
            Dict with session info and context metadata.
        """
        if not self._has_any_backend():
            return {"error": "No workspace backend configured"}

        try:
            be = self._get_backend(backend)
        except WorkspaceBackendError as exc:
            return {"error": str(exc)}

        backend_name = be.backend_name()

        instructions: str | None = task

        # Generate dispatch briefing from work item (overrides generic context)
        briefing: dict[str, Any] | None = None
        if work_item_id and self.work_item_manager:
            try:
                briefing = self.work_item_manager.generate_briefing(work_item_id)
            except Exception:
                logger.warning("Failed to generate briefing for work item %s", work_item_id, exc_info=True)

        agent = agent or self.default_agent
        session_title = title or f"cairn:{project}"
        if briefing:
            wi = briefing.get("work_item", {})
            session_title = title or f"cairn:{project} — {wi.get('title', '')[:50]}"
        elif instructions:
            session_title = f"cairn:{project} — {instructions[:50]}"

        # When we have a dispatch briefing, it replaces generic context injection
        # for ALL backends — both OpenCode and Claude Code get the same briefing.
        # Claude Code can still call orient() via MCP for additional context.
        if briefing:
            inject_context = False
        elif backend_name == "claude_code":
            # No briefing and no generic context — Claude Code uses MCP self-service
            inject_context = False

        # Create or fork session
        try:
            if fork_from and be.supports_fork():
                session = be.fork_session(fork_from)
                # Forked sessions already have full context — skip injection
                inject_context = False
                logger.info("Forked session %s from %s", session.id, fork_from)
            else:
                session = be.create_session(title=session_title)
        except WorkspaceBackendError as exc:
            logger.error("Failed to create %s session: %s", backend_name, exc)
            return {"error": str(exc)}

        result: dict[str, Any] = {
            "session_id": session.id,
            "title": session_title,
            "project": project,
            "agent": agent,
            "backend": backend_name,
            "context_injected": False,
            "task_sent": False,
        }
        if fork_from:
            result["forked_from"] = fork_from
        if work_item_id:
            result["work_item_id"] = work_item_id

        # Build a single message combining context + task.
        message_parts: list[str] = []

        # Dispatch briefing takes priority over generic context
        if briefing:
            briefing_text = self._format_briefing(briefing)
            message_parts.append(briefing_text)
            result["context_injected"] = True
            result["briefing"] = True
        elif inject_context:
            context = self.build_context(project, task=instructions, mode=context_mode)
            if context and "No prior context found" not in context:
                message_parts.append(f"[PROJECT CONTEXT]\n{context}")
                result["context_injected"] = True
                result["context_length"] = len(context)

        if instructions:
            message_parts.append(instructions)

        # Send as a single message so the agent sees one coherent prompt.
        if message_parts:
            combined = "\n\n---\n\n".join(message_parts)

            # Brief delay after session creation lets OpenCode finish MCP tool
            # initialization — without it K2.5 generates empty output on the
            # first async message (tools aren't available yet).
            # Claude Code doesn't need this delay.
            if backend_name == "opencode":
                time.sleep(3)

            try:
                send_kwargs: dict[str, Any] = {"agent": agent}
                if backend_name == "claude_code":
                    if risk_tier is not None:
                        send_kwargs["risk_tier"] = risk_tier
                    if model:
                        send_kwargs["model"] = model
                be.send_message_async(session.id, combined, **send_kwargs)
                result["task_sent"] = True
                logger.info("Task sent to session %s via %s (async)", session.id, backend_name)
            except WorkspaceBackendError as exc:
                logger.warning("Failed to send task to session %s: %s", session.id, exc)

        # Track in DB
        project_id = get_or_create_project(self.db, project)
        backend_metadata: dict[str, Any] = {}
        if risk_tier is not None:
            backend_metadata["risk_tier"] = risk_tier
        if model:
            backend_metadata["model"] = model
        if work_item_id:
            backend_metadata["work_item_id"] = str(work_item_id)
        row = self.db.execute_one(
            """
            INSERT INTO workspace_sessions
                (project_id, backend_session_id, agent, title, task, backend, backend_metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (project_id, session.id, agent, session_title, instructions,
             backend_name, json.dumps(backend_metadata)),
        )
        self.db.commit()
        result["id"] = row["id"]
        result["created_at"] = row["created_at"].isoformat()

        logger.info("Workspace session #%d created (backend=%s, session=%s, project=%s)",
                     row["id"], backend_name, session.id, project)
        return result

    @track_operation("workspace.send_message")
    def send_message(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        wait: bool = True,
    ) -> dict[str, Any]:
        """Send a message to a workspace session.

        Args:
            session_id: Backend session ID.
            text: Message text.
            agent: Override agent for this message.
            wait: If True, wait for response (sync). If False, fire-and-forget.

        Returns:
            Dict with response text and metadata.
        """
        if not self._has_any_backend():
            return {"error": "No workspace backend configured"}

        try:
            be = self._backend_for_session(session_id)
        except WorkspaceBackendError as exc:
            return {"error": str(exc)}

        try:
            if wait:
                msg = be.send_message(session_id, text, agent=agent)
                # Extract text from parts
                text_parts = [
                    p.get("text", "") for p in msg.parts if p.get("type") == "text"
                ]
                return {"session_id": session_id, "response": "\n".join(text_parts)}
            else:
                be.send_message_async(session_id, text, agent=agent)
                return {"session_id": session_id, "status": "sent"}
        except WorkspaceBackendError as exc:
            logger.error("Failed to send message to session %s: %s", session_id, exc)
            return {"error": str(exc)}

    @track_operation("workspace.get_session")
    def get_session(self, session_id: str) -> dict[str, Any]:
        """Get session details combining backend and Cairn data."""
        if not self._has_any_backend():
            return {"error": "No workspace backend configured"}

        try:
            be = self._backend_for_session(session_id)
            session = be.get_session(session_id)
            result: dict[str, Any] = {
                "session_id": session.id,
                "title": session.title,
                "created_at": session.created_at,
            }
        except WorkspaceBackendError as exc:
            result = {"session_id": session_id, "error": str(exc)}

        # Enrich with Cairn tracking data
        row = self.db.execute_one(
            "SELECT * FROM workspace_sessions WHERE backend_session_id = %s",
            (session_id,),
        )
        if row:
            result["project"] = self._get_project_name(row["project_id"])
            result["agent"] = row["agent"]
            result["task"] = row["task"]
            result["cairn_id"] = row["id"]
            result["backend"] = row["backend"]

        return result

    @track_operation("workspace.list_sessions")
    def list_sessions(self, project: str | None = None) -> list[dict[str, Any]]:
        """List workspace sessions, optionally filtered by project."""
        if project:
            project_id = get_project(self.db, project)
            if not project_id:
                return []
            rows = self.db.execute(
                """SELECT ws.*, p.name as project_name
                   FROM workspace_sessions ws
                   JOIN projects p ON p.id = ws.project_id
                   WHERE ws.project_id = %s
                   ORDER BY ws.created_at DESC LIMIT 50""",
                (project_id,),
            )
        else:
            rows = self.db.execute(
                """SELECT ws.*, p.name as project_name
                   FROM workspace_sessions ws
                   JOIN projects p ON p.id = ws.project_id
                   ORDER BY ws.created_at DESC LIMIT 50""",
            )

        return [
            {
                "id": r["id"],
                "session_id": r["backend_session_id"],
                "project": r["project_name"],
                "agent": r["agent"],
                "title": r["title"],
                "task": r.get("task"),
                "backend": r.get("backend", "opencode"),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
            for r in rows
        ]

    @track_operation("workspace.abort_session")
    def abort_session(self, session_id: str) -> dict[str, Any]:
        """Abort a running session."""
        if not self._has_any_backend():
            return {"error": "No workspace backend configured"}
        try:
            be = self._backend_for_session(session_id)
            be.abort_session(session_id)
            return {"session_id": session_id, "status": "aborted"}
        except WorkspaceBackendError as exc:
            return {"error": str(exc)}

    @track_operation("workspace.delete_session")
    def delete_session(self, session_id: str) -> dict[str, Any]:
        """Delete a workspace session from both backend and Cairn tracking."""
        if not self._has_any_backend():
            return {"error": "No workspace backend configured"}

        try:
            be = self._backend_for_session(session_id)
            be.delete_session(session_id)
        except WorkspaceBackendError as exc:
            logger.warning("Failed to delete backend session %s: %s", session_id, exc)

        self.db.execute(
            "DELETE FROM workspace_sessions WHERE backend_session_id = %s",
            (session_id,),
        )
        self.db.commit()
        return {"session_id": session_id, "status": "deleted"}

    @track_operation("workspace.get_diff")
    def get_diff(self, session_id: str) -> list[dict[str, Any]]:
        """Get file diffs from a session."""
        if not self._has_any_backend():
            return []
        try:
            be = self._backend_for_session(session_id)
            return be.get_diff(session_id)
        except WorkspaceBackendError as exc:
            logger.warning("Failed to get diff for session %s: %s", session_id, exc)
            return []

    @track_operation("workspace.health")
    def health(self) -> dict[str, Any]:
        """Check health of all configured backends.

        Returns overall status plus per-backend details.
        Overall is 'healthy' if any backend is healthy.
        """
        if not self._backends:
            return {"status": "not_configured"}

        backends_health: dict[str, dict[str, Any]] = {}
        any_healthy = False

        for name, be in self._backends.items():
            try:
                h = be.health()
                status = "healthy" if h.healthy else "unhealthy"
                backends_health[name] = {"status": status, "version": h.version}
                if h.healthy:
                    any_healthy = True
            except Exception as exc:
                backends_health[name] = {"status": "unreachable", "error": str(exc)}

        return {
            "status": "healthy" if any_healthy else "unhealthy",
            "backends": backends_health,
        }

    @track_operation("workspace.get_messages")
    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Get messages from a session.

        Returns a list of message dicts with id, role, parts, and created_at.
        """
        if not self._has_any_backend():
            return []
        try:
            be = self._backend_for_session(session_id)
            messages = be.get_messages(session_id)
            return [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "parts": msg.parts,
                    "created_at": msg.created_at,
                }
                for msg in messages
            ]
        except WorkspaceBackendError as exc:
            logger.warning("Failed to get messages for session %s: %s", session_id, exc)
            return []

    @track_operation("workspace.list_agents")
    def list_agents(self) -> list[dict[str, Any]]:
        """List available agents from all backends."""
        all_agents: list[dict[str, Any]] = []
        for name, be in self._backends.items():
            try:
                agents = be.list_agents()
                for a in agents:
                    all_agents.append({
                        "id": a.id,
                        "name": a.name,
                        "description": a.description,
                        "model": a.model,
                        "backend": a.backend or name,
                    })
            except WorkspaceBackendError as exc:
                logger.warning("Failed to list agents from %s: %s", name, exc)
        return all_agents

    def list_backends(self) -> list[dict[str, Any]]:
        """List all configured backends with capabilities and health."""
        result: list[dict[str, Any]] = []
        for name, be in self._backends.items():
            entry: dict[str, Any] = {
                "name": name,
                "capabilities": be.capabilities(),
                "is_default": name == self._default_backend,
            }
            try:
                h = be.health()
                entry["status"] = "healthy" if h.healthy else "unhealthy"
                entry["version"] = h.version
            except Exception as exc:
                entry["status"] = "unreachable"
                entry["error"] = str(exc)
            result.append(entry)
        return result

    # -- private helpers -----------------------------------------------------

    def _format_briefing(self, briefing: dict[str, Any]) -> str:
        """Format a work item dispatch briefing into a prompt for the agent.

        Produces a structured assignment that tells the agent exactly what it's
        working on, including acceptance criteria, constraints, and linked context.
        """
        wi = briefing.get("work_item", {})
        sections: list[str] = []

        sections.append("[DISPATCH BRIEFING]")
        sections.append(f"You are assigned to work item **{wi.get('short_id', '?')}**: {wi.get('title', 'Untitled')}")
        sections.append(f"Risk tier: {wi.get('risk_tier', 0)} ({wi.get('risk_label', 'patrol')})")

        if wi.get("description"):
            sections.append(f"\n## Description\n{wi['description']}")

        if wi.get("acceptance_criteria"):
            sections.append(f"\n## Acceptance Criteria\n{wi['acceptance_criteria']}")

        # Parent chain for hierarchy context
        parent_chain = briefing.get("parent_chain", [])
        if parent_chain:
            chain_str = " → ".join(f"{p['short_id']}: {p['title']}" for p in parent_chain)
            sections.append(f"\n## Parent Context\n{chain_str} → **{wi.get('short_id', '?')}** (you are here)")

        # Cascaded constraints
        constraints = briefing.get("constraints", {})
        if constraints:
            constraint_lines = [f"- **{k}**: {v}" for k, v in constraints.items()]
            sections.append("\n## Constraints\n" + "\n".join(constraint_lines))

        # Linked memories for context
        context = briefing.get("context", [])
        if context:
            mem_lines = [f"- [{c.get('type', 'note')}] {c.get('summary', 'no summary')}" for c in context]
            sections.append("\n## Linked Context\n" + "\n".join(mem_lines))

        # Gate history — so re-dispatched agents know what was already decided
        gate_response = wi.get("gate_response")
        gate_data = wi.get("gate_data")
        if gate_response:
            sections.append("\n## Prior Gate (Resolved)")
            if gate_data and gate_data.get("question"):
                sections.append(f"**Question asked:** {gate_data['question']}")
                if gate_data.get("options"):
                    for opt in gate_data["options"]:
                        sections.append(f"  - {opt}")
            resp_text = gate_response.get("text", str(gate_response)) if isinstance(gate_response, dict) else str(gate_response)
            sections.append(f"**Human answered:** {resp_text}")
            sections.append("Do NOT re-ask this question. Proceed with the chosen option.")

        sections.append("\n## Instructions")
        sections.append("- Update this work item's status as you progress (claim → in_progress → done)")
        sections.append("- Use heartbeat to report progress")
        sections.append("- Set a gate if you need human input before proceeding")
        sections.append("- You may call orient() or search() via MCP for additional project context")

        return "\n".join(sections)

    def _format_rules(self, rules: list[dict], budget: int) -> str:
        """Format rules section within a token budget."""
        header = "## Rules & Conventions\n"
        lines: list[str] = []
        tokens_used = estimate_tokens(header)
        for r in rules:
            content = truncate_to_budget(r["content"], 200, suffix="...")
            line = f"- {content}"
            line_tokens = estimate_tokens(line)
            if budget > 0 and tokens_used + line_tokens > budget and lines:
                break
            lines.append(line)
            tokens_used += line_tokens
        return header + "\n".join(lines)

    def _format_memories(self, memories: list[dict], budget: int) -> str:
        """Format memories section within a token budget."""
        header = "## Relevant Context\n"
        lines: list[str] = []
        tokens_used = estimate_tokens(header)
        for m in memories:
            summary = m.get("summary") or m.get("content", "")[:150]
            line = f"- [{m.get('memory_type', 'note')}] {summary}"
            line_tokens = estimate_tokens(line)
            if budget > 0 and tokens_used + line_tokens > budget and lines:
                break
            lines.append(line)
            tokens_used += line_tokens
        return header + "\n".join(lines)

    def _format_trail(self, trail: list[dict], budget: int) -> str:
        """Format trail section within a token budget."""
        header = "## Recent Sessions\n"
        lines: list[str] = []
        tokens_used = estimate_tokens(header)
        for c in trail:
            title = c.get("title") or c.get("session_name", "untitled")
            narrative = c.get("narrative", "")[:150]
            line = f"- **{title}**: {narrative}"
            line_tokens = estimate_tokens(line)
            if budget > 0 and tokens_used + line_tokens > budget and lines:
                break
            lines.append(line)
            tokens_used += line_tokens
        return header + "\n".join(lines)

    def _format_tasks(self, tasks: list[dict], budget: int) -> str:
        """Format tasks section within a token budget."""
        header = "## Pending Tasks\n"
        lines: list[str] = []
        tokens_used = estimate_tokens(header)
        for t in tasks[:5]:
            line = f"- {t['description']}"
            line_tokens = estimate_tokens(line)
            if budget > 0 and tokens_used + line_tokens > budget and lines:
                break
            lines.append(line)
            tokens_used += line_tokens
        return header + "\n".join(lines)

    def _fetch_rules(self, project: str, *, include_global: bool = True) -> list[dict]:
        """Fetch rules for a project, optionally including __global__."""
        if include_global:
            rows = self.db.execute(
                """
                SELECT m.content, m.importance
                FROM memories m
                LEFT JOIN projects p ON p.id = m.project_id
                WHERE m.memory_type = 'rule'
                  AND m.is_active = true
                  AND (p.name = %s OR p.name = '__global__')
                ORDER BY m.importance DESC
                LIMIT 20
                """,
                (project,),
            )
        else:
            rows = self.db.execute(
                """
                SELECT m.content, m.importance
                FROM memories m
                LEFT JOIN projects p ON p.id = m.project_id
                WHERE m.memory_type = 'rule'
                  AND m.is_active = true
                  AND p.name = %s
                ORDER BY m.importance DESC
                LIMIT 10
                """,
                (project,),
            )
        return [dict(r) for r in rows]

    def _fetch_trail(self, project: str, limit: int = 3) -> list[dict]:
        """Fetch recent session activity for a project.

        v0.37.0: queries recent memories grouped by session instead of cairns table.
        """
        project_id = get_project(self.db, project)
        if not project_id:
            return []
        rows = self.db.execute(
            """
            SELECT session_name, MAX(summary) AS narrative,
                   MAX(created_at) AS set_at, COUNT(*) AS memory_count
            FROM memories
            WHERE project_id = %s AND is_active = true
              AND session_name IS NOT NULL
            GROUP BY session_name
            ORDER BY MAX(created_at) DESC
            LIMIT %s
            """,
            (project_id, limit),
        )
        return [
            {
                "session_name": r["session_name"],
                "title": r["session_name"],
                "narrative": r["narrative"] or "",
                "set_at": r["set_at"],
            }
            for r in rows
        ]

    def _search_memories(self, project: str, query: str, limit: int = 5) -> list[dict]:
        """Quick keyword search for relevant memories."""
        project_id = get_project(self.db, project)
        if not project_id:
            return []
        rows = self.db.execute(
            """
            SELECT id, content, memory_type, summary, importance
            FROM memories
            WHERE project_id = %s AND is_active = true
              AND to_tsvector('english', content) @@ plainto_tsquery('english', %s)
            ORDER BY importance DESC
            LIMIT %s
            """,
            (project_id, query, limit),
        )
        return [dict(r) for r in rows]

    def _fetch_tasks(self, project: str) -> list[dict]:
        """Fetch pending tasks for a project."""
        project_id = get_project(self.db, project)
        if not project_id:
            return []
        rows = self.db.execute(
            """
            SELECT id, description, created_at
            FROM tasks
            WHERE project_id = %s AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT 10
            """,
            (project_id,),
        )
        return [dict(r) for r in rows]

    def _get_project_name(self, project_id: int) -> str | None:
        """Look up project name by ID."""
        row = self.db.execute_one(
            "SELECT name FROM projects WHERE id = %s", (project_id,),
        )
        return row["name"] if row else None
