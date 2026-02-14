"""Workspace manager: bridge between Cairn context and OpenCode execution.

Assembles context from Cairn (rules, memories, project docs, cairn trail)
and manages OpenCode sessions with that context injected.
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
from cairn.core.messages import MessageManager
from cairn.core.utils import get_or_create_project, get_project
from cairn.integrations.opencode import OpenCodeClient, OpenCodeError
from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Manages workspace sessions bridging Cairn memory and OpenCode execution.

    Responsibilities:
    - Assemble context from Cairn (rules, recent memories, project docs, trail)
    - Create OpenCode sessions with injected context
    - Track session→project mapping for cairn lifecycle
    """

    def __init__(
        self,
        db: Database,
        opencode: OpenCodeClient | None = None,
        *,
        message_manager: MessageManager | None = None,
        default_agent: str = "cairn-build",
        budget_tokens: int = 6000,
    ):
        self.db = db
        self.opencode = opencode
        self.message_manager = message_manager
        self.default_agent = default_agent
        self.budget_tokens = budget_tokens

    # -- context assembly ----------------------------------------------------

    @track_operation("workspace.build_context")
    def build_context(
        self,
        project: str,
        *,
        task: str | None = None,
        mode: str = "focused",
    ) -> str:
        """Assemble Cairn context into a system prompt for an OpenCode session.

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
        message_id: int | None = None,
        fork_from: str | None = None,
        title: str | None = None,
        agent: str | None = None,
        inject_context: bool = True,
        context_mode: str = "focused",
    ) -> dict[str, Any]:
        """Create an OpenCode session with Cairn context injected.

        Instructions can come from multiple sources:
        - ``task``: Raw text description.
        - ``message_id``: Read instructions from a Cairn message.
        - ``fork_from``: Fork an existing OpenCode session (full history carry-over).
        - All can be combined.

        When forking, the new session inherits the full conversation history
        of the parent — all analysis, decisions, and file changes. Context
        injection is skipped (parent already has it). The task/message is sent
        as a continuation message.

        After context injection, instructions are sent as the first real
        message so the agent starts working autonomously.

        Args:
            project: Cairn project name for context.
            task: Optional task description.
            message_id: Optional Cairn message ID to read instructions from.
            fork_from: Optional OpenCode session ID to fork from.
            title: Session title (auto-generated if omitted).
            agent: Agent to use (defaults to workspace default).
            inject_context: Whether to inject Cairn context as first message.
            context_mode: "focused" (default, lean) or "full" (grimoire + trail).

        Returns:
            Dict with session info and context metadata.
        """
        if not self.opencode:
            return {"error": "OpenCode not configured (set CAIRN_OPENCODE_URL)"}

        # Resolve instructions — message_id is passed by reference, not inlined.
        # The agent looks it up via cairn_messages at runtime.
        instructions: str | None = task
        source_message: dict | None = None
        if message_id and self.message_manager:
            source_message = self.message_manager.get(message_id)
            if not source_message:
                return {"error": f"Message #{message_id} not found"}
            msg_project = source_message.get("project", project)
            # Tell the agent WHERE to find instructions, don't inline them.
            # Skip context injection — the message itself IS the context.
            ref = f"Your task is in Cairn message #{message_id} (project: {msg_project}). Read it with cairn_messages(action=\"inbox\", project=\"{msg_project}\"), find message id={message_id}, and execute its instructions."
            if task:
                instructions = f"{ref}\n\nAdditional context: {task}"
            else:
                instructions = ref
            inject_context = False
            self.message_manager.mark_read(message_id)

        agent = agent or self.default_agent
        session_title = title or f"cairn:{project}"
        if instructions:
            session_title = f"cairn:{project} — {instructions[:50]}"

        # Create or fork session
        try:
            if fork_from:
                session = self.opencode.fork_session(fork_from)
                # Forked sessions already have full context — skip injection
                inject_context = False
                logger.info("Forked session %s from %s", session.id, fork_from)
            else:
                session = self.opencode.create_session(title=session_title)
        except OpenCodeError as exc:
            logger.error("Failed to create OpenCode session: %s", exc)
            return {"error": str(exc)}

        result: dict[str, Any] = {
            "session_id": session.id,
            "title": session_title,
            "project": project,
            "agent": agent,
            "context_injected": False,
            "task_sent": False,
        }
        if source_message:
            result["source_message_id"] = message_id
        if fork_from:
            result["forked_from"] = fork_from

        # Build a single message combining context + task.
        # OpenCode already injects agent prompt, AGENTS.md, and environment
        # into the system prompt. Sending context as a separate no_reply
        # message creates two consecutive user messages which confuses models.
        message_parts: list[str] = []

        if inject_context:
            context = self.build_context(project, task=instructions, mode=context_mode)
            if context and "No prior context found" not in context:
                message_parts.append(f"[PROJECT CONTEXT]\n{context}")
                result["context_injected"] = True
                result["context_length"] = len(context)

        if instructions:
            message_parts.append(instructions)

        # Send as a single message so the agent sees one coherent prompt.
        # Brief delay after session creation lets OpenCode finish MCP tool
        # initialization — without it K2.5 generates empty output on the
        # first async message (tools aren't available yet).
        if message_parts:
            combined = "\n\n---\n\n".join(message_parts)
            time.sleep(3)
            try:
                self.opencode.send_message_async(
                    session.id,
                    combined,
                    agent=agent,
                )
                result["task_sent"] = True
                logger.info("Task sent to session %s (async)", session.id)
            except OpenCodeError as exc:
                logger.warning("Failed to send task to session %s: %s", session.id, exc)

        # Track in DB
        project_id = get_or_create_project(self.db, project)
        row = self.db.execute_one(
            """
            INSERT INTO workspace_sessions (project_id, opencode_session_id, agent, title, task)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (project_id, session.id, agent, session_title, instructions),
        )
        self.db.commit()
        result["id"] = row["id"]
        result["created_at"] = row["created_at"].isoformat()

        logger.info("Workspace session #%d created (opencode=%s, project=%s)",
                     row["id"], session.id, project)
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
        """Send a message to an OpenCode session.

        Args:
            session_id: OpenCode session ID.
            text: Message text.
            agent: Override agent for this message.
            wait: If True, wait for response (sync). If False, fire-and-forget.

        Returns:
            Dict with response text and metadata.
        """
        if not self.opencode:
            return {"error": "OpenCode not configured"}

        try:
            if wait:
                reply = self.opencode.send_and_collect_text(
                    session_id, text, agent=agent,
                )
                return {"session_id": session_id, "response": reply}
            else:
                self.opencode.send_message_async(session_id, text, agent=agent)
                return {"session_id": session_id, "status": "sent"}
        except OpenCodeError as exc:
            logger.error("Failed to send message to session %s: %s", session_id, exc)
            return {"error": str(exc)}

    @track_operation("workspace.get_session")
    def get_session(self, session_id: str) -> dict[str, Any]:
        """Get session details combining OpenCode and Cairn data."""
        if not self.opencode:
            return {"error": "OpenCode not configured"}

        try:
            session = self.opencode.get_session(session_id)
            result = {
                "session_id": session.id,
                "title": session.title,
                "created_at": session.created_at,
            }

            # Enrich with Cairn tracking data
            row = self.db.execute_one(
                "SELECT * FROM workspace_sessions WHERE opencode_session_id = %s",
                (session_id,),
            )
            if row:
                result["project"] = self._get_project_name(row["project_id"])
                result["agent"] = row["agent"]
                result["task"] = row["task"]
                result["cairn_id"] = row["id"]

            return result
        except OpenCodeError as exc:
            return {"error": str(exc)}

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
                "session_id": r["opencode_session_id"],
                "project": r["project_name"],
                "agent": r["agent"],
                "title": r["title"],
                "task": r.get("task"),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
            for r in rows
        ]

    @track_operation("workspace.abort_session")
    def abort_session(self, session_id: str) -> dict[str, Any]:
        """Abort a running OpenCode session."""
        if not self.opencode:
            return {"error": "OpenCode not configured"}
        try:
            self.opencode.abort_session(session_id)
            return {"session_id": session_id, "status": "aborted"}
        except OpenCodeError as exc:
            return {"error": str(exc)}

    @track_operation("workspace.delete_session")
    def delete_session(self, session_id: str) -> dict[str, Any]:
        """Delete a workspace session from both OpenCode and Cairn tracking."""
        if not self.opencode:
            return {"error": "OpenCode not configured"}

        try:
            self.opencode.delete_session(session_id)
        except OpenCodeError as exc:
            logger.warning("Failed to delete OpenCode session %s: %s", session_id, exc)

        self.db.execute(
            "DELETE FROM workspace_sessions WHERE opencode_session_id = %s",
            (session_id,),
        )
        self.db.commit()
        return {"session_id": session_id, "status": "deleted"}

    @track_operation("workspace.get_diff")
    def get_diff(self, session_id: str) -> list[dict[str, Any]]:
        """Get file diffs from an OpenCode session."""
        if not self.opencode:
            return []
        try:
            return self.opencode.get_diff(session_id)
        except OpenCodeError as exc:
            logger.warning("Failed to get diff for session %s: %s", session_id, exc)
            return []

    @track_operation("workspace.health")
    def health(self) -> dict[str, Any]:
        """Check OpenCode worker health."""
        if not self.opencode:
            return {"status": "not_configured"}
        try:
            h = self.opencode.health()
            return {
                "status": "healthy" if h.healthy else "unhealthy",
                "version": h.version,
            }
        except OpenCodeError as exc:
            return {"status": "unreachable", "error": str(exc)}

    @track_operation("workspace.get_messages")
    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Get messages from an OpenCode session.

        Returns a list of message dicts with id, role, parts, and created_at.
        """
        if not self.opencode:
            return []
        try:
            envelopes = self.opencode.get_messages(session_id)
            return [
                {
                    "id": env.info.id,
                    "role": env.info.role,
                    "parts": env.parts,
                    "created_at": env.info.created_at,
                }
                for env in envelopes
            ]
        except OpenCodeError as exc:
            logger.warning("Failed to get messages for session %s: %s", session_id, exc)
            return []

    @track_operation("workspace.list_agents")
    def list_agents(self) -> list[dict[str, Any]]:
        """List available agents from OpenCode."""
        if not self.opencode:
            return []
        try:
            agents = self.opencode.list_agents()
            return [
                {
                    "id": a.id,
                    "name": a.name,
                    "description": a.description,
                    "model": a.model,
                }
                for a in agents
            ]
        except OpenCodeError as exc:
            logger.warning("Failed to list agents: %s", exc)
            return []

    # -- private helpers -----------------------------------------------------

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
        """Fetch recent cairns for a project."""
        project_id = get_project(self.db, project)
        if not project_id:
            return []
        rows = self.db.execute(
            """
            SELECT id, session_name, title, narrative, set_at
            FROM cairns
            WHERE project_id = %s
            ORDER BY set_at DESC
            LIMIT %s
            """,
            (project_id, limit),
        )
        return [dict(r) for r in rows]

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
