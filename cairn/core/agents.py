"""Agent type definitions and registry — capability-based agent archetypes.

Part of ca-150/ca-155: agent definitions with tool restrictions,
capability declarations, file pattern scoping, and risk tier enforcement.

Defines agent roles (worker, coordinator, researcher, planner, reviewer) with:
- Tool allowlists/blocklists (what the agent CAN/CANNOT use)
- Capability declarations (read_files, write_files, dispatch_agents, etc.)
- File pattern restrictions (glob patterns for allowed file modifications)
- Max risk tier (highest risk work this agent can claim)
- Briefing context (role-specific instructions appended to dispatch)
- Admiral at the Helm enforcement for coordinators
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field


# Recognized capability names
CAPABILITIES = frozenset({
    "read_files",
    "write_files",
    "execute_code",
    "dispatch_agents",
    "create_work_items",
    "modify_memories",
    "review_deliverables",
    "search_context",
})


@dataclass(frozen=True)
class AgentDefinition:
    """Defines an agent archetype with capabilities and restrictions."""

    name: str
    role: str  # "worker", "coordinator", "researcher", "planner", "reviewer"
    description: str
    default_risk_tier: int = 1

    # Maximum risk tier this agent can be dispatched for.
    # None = no limit (can take any risk level).
    max_risk_tier: int | None = None

    # Declared capabilities — what this agent can conceptually do.
    capabilities: frozenset[str] = field(default_factory=frozenset)

    # Tools the agent is allowed to use. Empty = unrestricted (worker default).
    allowed_tools: frozenset[str] = field(default_factory=frozenset)

    # Tools the agent must NOT use. Takes priority over allowed_tools.
    blocked_tools: frozenset[str] = field(default_factory=frozenset)

    # Glob patterns for files this agent can modify. Empty = unrestricted.
    file_patterns: frozenset[str] = field(default_factory=frozenset)

    # Role-specific system prompt appended to the briefing.
    system_prompt: str = ""

    @property
    def is_coordinator(self) -> bool:
        return self.role == "coordinator"

    @property
    def is_restricted(self) -> bool:
        """True if this agent has tool or file restrictions."""
        return bool(self.allowed_tools) or bool(self.blocked_tools) or bool(self.file_patterns)

    def can_use_tool(self, tool_name: str) -> bool:
        """Check if the agent is allowed to use a given tool."""
        if tool_name in self.blocked_tools:
            return False
        if self.allowed_tools:
            return tool_name in self.allowed_tools
        return True  # No allowlist = unrestricted

    def can_modify_file(self, file_path: str) -> bool:
        """Check if the agent is allowed to modify a given file.

        Returns True if no file_patterns are set (unrestricted) or if
        the file matches at least one pattern.
        """
        if not self.file_patterns:
            return True  # No restrictions
        return any(fnmatch.fnmatch(file_path, p) for p in self.file_patterns)

    def has_capability(self, capability: str) -> bool:
        """Check if this agent declares a given capability."""
        if not self.capabilities:
            return True  # No declarations = assumed capable
        return capability in self.capabilities

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "default_risk_tier": self.default_risk_tier,
            "max_risk_tier": self.max_risk_tier,
            "capabilities": sorted(self.capabilities) if self.capabilities else [],
            "allowed_tools": sorted(self.allowed_tools) if self.allowed_tools else [],
            "blocked_tools": sorted(self.blocked_tools) if self.blocked_tools else [],
            "file_patterns": sorted(self.file_patterns) if self.file_patterns else [],
            "is_coordinator": self.is_coordinator,
            "system_prompt": self.system_prompt[:200] + "..." if len(self.system_prompt) > 200 else self.system_prompt,
        }


# ============================================================
# Built-in agent definitions
# ============================================================

# Tools available to coordinators — orchestration-focused
_COORDINATOR_TOOLS = frozenset({
    # Work item management
    "work_items", "dispatch",
    # Observation & context
    "orient", "search", "recall", "rules", "insights",
    "code_query", "code_index",
    # Planning & deliberation
    "think", "projects",
    # Deliverable creation (synthesis output)
    "store",
    # Task tracking
    "tasks",
})

# Tools blocked from coordinators — no direct implementation
_COORDINATOR_BLOCKED = frozenset({
    "Edit", "Write", "Bash", "NotebookEdit",
})

_COORDINATOR_PROMPT = """You are a COORDINATOR agent. Your role is to orchestrate, not implement.

## What you CAN do:
- Decompose epics into subtasks (work_items action=add_child)
- Dispatch workers to implement subtasks (dispatch)
- Monitor worker progress via heartbeats and work item status
- Search and recall context to inform decisions (orient, search, recall)
- Use thinking sequences for deliberation on complex decisions
- Create deliverables that synthesize worker outputs
- Set gates when human input is needed

## What you CANNOT do:
- Write, edit, or create files directly
- Run shell commands
- Modify code
- Claim implementation tasks

## Decision Protocol:
1. When uncertain, use think() to reason through options
2. When blocked on a human decision, set a gate (gate_type=human)
3. When a worker is stuck, re-dispatch with clearer instructions
4. When all subtasks complete, synthesize results into an epic deliverable

## Anti-patterns to avoid:
- Split Keel: Never dispatch two workers to the same file
- Drifting Anchorage: Don't expand scope beyond the original epic
- Skeleton Crew: Don't over-decompose — 3-7 subtasks per epic is ideal
"""

_WORKER_PROMPT = """You are a WORKER agent. Focus on implementation.

## Your responsibilities:
- Implement the specific task assigned to you
- Heartbeat progress regularly (every few minutes of active work)
- Create a deliverable when your work is complete
- Set a gate if you need human input or are stuck

## Guidelines:
- Stay focused on your assigned task — don't expand scope
- If you discover related work needed, note it but don't do it
- Prefer small, tested changes over large sweeping modifications
"""

_RESEARCHER_PROMPT = """You are a RESEARCHER agent. Explore and analyze.

## Your responsibilities:
- Investigate the question or topic thoroughly
- Search memories, code, and documentation for relevant context
- Create a structured deliverable with your findings
- Identify follow-up questions or areas needing deeper investigation

## Guidelines:
- Be thorough but time-bound — deliver findings within your context window
- Cite sources (memory IDs, file paths, URLs) for all claims
- Distinguish facts from inferences
"""

_PLANNER_PROMPT = """You are a PLANNER agent. Design implementation strategies.

## Your responsibilities:
- Analyze the epic or feature request
- Break it into concrete, implementable subtasks
- Identify dependencies and sequencing
- Estimate risk levels for each subtask
- Create a deliverable with the implementation plan

## Guidelines:
- Each subtask should be independently dispatchable
- Consider existing architecture and patterns
- Flag areas of high risk or uncertainty
"""

_REVIEWER_PROMPT = """You are a REVIEWER agent. Validate deliverables and code quality.

## Your responsibilities:
- Review deliverables from worker agents for completeness and quality
- Verify code changes follow project conventions and patterns
- Check for common issues (missing tests, security concerns, style violations)
- Provide structured feedback via review comments

## Guidelines:
- Be constructive — identify specific issues with suggested fixes
- Approve deliverables that meet acceptance criteria
- Reject with clear reasons and actionable feedback
- Do not implement fixes yourself — set a gate or re-dispatch to the worker
"""

# Capability sets for built-in agents
_WORKER_CAPABILITIES = frozenset({
    "read_files", "write_files", "execute_code", "search_context",
})

_COORDINATOR_CAPABILITIES = frozenset({
    "dispatch_agents", "create_work_items", "search_context",
    "review_deliverables",
})

_RESEARCHER_CAPABILITIES = frozenset({
    "read_files", "search_context",
})

_PLANNER_CAPABILITIES = frozenset({
    "read_files", "search_context", "create_work_items",
})

_REVIEWER_CAPABILITIES = frozenset({
    "read_files", "search_context", "review_deliverables",
})


BUILTIN_AGENTS: dict[str, AgentDefinition] = {
    "cairn-worker": AgentDefinition(
        name="cairn-worker",
        role="worker",
        description="General-purpose implementation agent — writes code, edits files, runs tests",
        default_risk_tier=1,
        capabilities=_WORKER_CAPABILITIES,
        system_prompt=_WORKER_PROMPT,
    ),
    "cairn-build": AgentDefinition(
        name="cairn-build",
        role="worker",
        description="Build agent — focused on code changes and feature implementation",
        default_risk_tier=1,
        capabilities=_WORKER_CAPABILITIES,
        system_prompt=_WORKER_PROMPT,
    ),
    "cairn-coordinator": AgentDefinition(
        name="cairn-coordinator",
        role="coordinator",
        description="Orchestration agent — decomposes, dispatches, monitors, and synthesizes",
        default_risk_tier=1,
        max_risk_tier=None,  # Coordinators can orchestrate any risk level
        capabilities=_COORDINATOR_CAPABILITIES,
        allowed_tools=_COORDINATOR_TOOLS,
        blocked_tools=_COORDINATOR_BLOCKED,
        system_prompt=_COORDINATOR_PROMPT,
    ),
    "cairn-research": AgentDefinition(
        name="cairn-research",
        role="researcher",
        description="Research agent — explores codebases, searches context, analyzes findings",
        default_risk_tier=3,  # Research-only — read access
        max_risk_tier=3,  # Cannot take action-heavy work
        capabilities=_RESEARCHER_CAPABILITIES,
        system_prompt=_RESEARCHER_PROMPT,
    ),
    "cairn-plan": AgentDefinition(
        name="cairn-plan",
        role="planner",
        description="Planning agent — designs implementation strategies and breaks down epics",
        default_risk_tier=2,  # Read-heavy with limited write
        max_risk_tier=2,
        capabilities=_PLANNER_CAPABILITIES,
        system_prompt=_PLANNER_PROMPT,
    ),
    "cairn-reviewer": AgentDefinition(
        name="cairn-reviewer",
        role="reviewer",
        description="Review agent — validates deliverables, checks code quality, provides feedback",
        default_risk_tier=2,
        max_risk_tier=2,  # Read-heavy, no direct implementation
        capabilities=_REVIEWER_CAPABILITIES,
        system_prompt=_REVIEWER_PROMPT,
    ),
}


class AgentRegistry:
    """Registry of available agent definitions.

    Combines built-in definitions with any custom definitions
    loaded from config or database.
    """

    def __init__(self):
        self._agents: dict[str, AgentDefinition] = dict(BUILTIN_AGENTS)

    def get(self, name: str) -> AgentDefinition | None:
        """Look up an agent definition by name."""
        return self._agents.get(name)

    def get_or_default(self, name: str | None) -> AgentDefinition:
        """Get agent definition, falling back to worker."""
        if name and name in self._agents:
            return self._agents[name]
        return self._agents["cairn-worker"]

    def register(self, definition: AgentDefinition) -> None:
        """Register a custom agent definition."""
        self._agents[definition.name] = definition

    def list(self) -> list[AgentDefinition]:
        """List all registered agent definitions."""
        return sorted(self._agents.values(), key=lambda d: d.name)

    def list_by_role(self, role: str) -> list[AgentDefinition]:
        """List agents with a specific role."""
        return [d for d in self._agents.values() if d.role == role]

    def to_dict(self) -> list[dict]:
        return [d.to_dict() for d in self.list()]


def validate_dispatch(
    agent_def: AgentDefinition,
    work_item: dict,
) -> list[str]:
    """Validate that an agent can be dispatched for a work item.

    Returns a list of validation errors (empty = valid).
    """
    errors: list[str] = []

    # Admiral at the Helm: coordinators cannot claim implementation tasks
    if agent_def.is_coordinator:
        item_type = work_item.get("item_type", "task")

        # Coordinators should work on epics, not leaf tasks
        if item_type == "subtask":
            errors.append(
                f"Coordinator '{agent_def.name}' should not be dispatched to subtasks. "
                "Coordinators decompose and dispatch — they don't implement."
            )

    # Risk tier ceiling: agent cannot take work above its max tier
    work_risk = work_item.get("risk_tier")
    if (
        agent_def.max_risk_tier is not None
        and work_risk is not None
        and work_risk < agent_def.max_risk_tier  # Lower number = higher risk
    ):
        errors.append(
            f"Agent '{agent_def.name}' max risk tier is {agent_def.max_risk_tier} "
            f"but work item requires tier {work_risk}. "
            "Lower tier numbers indicate higher-risk work."
        )

    return errors
