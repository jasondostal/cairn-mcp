"""Centralized constants and enums for Cairn core modules."""

from __future__ import annotations


# ============================================================
# Memory
# ============================================================

VALID_MEMORY_TYPES = [
    "note", "decision", "rule", "code-snippet", "learning",
    "research", "discussion", "progress", "task", "debug", "design",
]

MEMORY_TYPE_DEFAULT = "note"
IMPORTANCE_DEFAULT = 0.5

# ============================================================
# Working Memory
# ============================================================

VALID_WM_TYPES = [
    "hypothesis", "question", "tension", "connection", "thread", "intuition",
]

VALID_WM_RESOLUTION_TYPES = [
    "memory", "belief", "work_item", "decision", "thinking_sequence",
]

# Default salience by item type
WM_DEFAULT_SALIENCE = {
    "hypothesis": 0.7,
    "question": 0.6,
    "tension": 0.8,
    "connection": 0.5,
    "thread": 0.6,
    "intuition": 0.7,
}

WM_SALIENCE_DECAY_RATE = 0.97     # per-day multiplier
WM_SALIENCE_BOOST_FLOOR = 0.7     # minimum salience after boost
WM_SALIENCE_ARCHIVE_THRESHOLD = 0.1

# Content size management
AUTO_SUMMARIZE_EMBED_THRESHOLD = 8000  # chars — use summary for embedding above this

# Input limits
MAX_CONTENT_SIZE = 500_000      # ~500KB — single memory ceiling (embedding quality
                                # is handled by AUTO_SUMMARIZE_EMBED_THRESHOLD above)
MAX_INGEST_SIZE = 100_000_000   # ~100MB — ingest pipeline chunks automatically via
                                # Chonkie; cost is proportional to chunk count, not size
MAX_NAME_LENGTH = 255  # project, session, branch names
MAX_TAGS = 20
MAX_TAG_LENGTH = 100
MAX_SEARCH_QUERY = 2000
MAX_RECALL_IDS = 10
MAX_LIMIT = 100
VALID_SEARCH_MODES = ["semantic", "keyword", "vector"]

# Contradiction handling
CONTRADICTION_PENALTY = 0.5          # score multiplier for contradicted memories in search
CONTRADICTION_ESCALATION_THRESHOLD = 0.7  # min importance to trigger conflict escalation on store

# RRF weight configurations — dynamically selected based on available signals.
# All weight sets must sum to 1.0.
RRF_WEIGHTS_DEFAULT = {
    "vector": 0.46,
    "recency": 0.18,
    "keyword": 0.18,
    "tag": 0.10,
    "importance": 0.08,
}
RRF_WEIGHTS_WITH_ENTITIES = {
    "vector": 0.37,
    "entity": 0.18,
    "keyword": 0.18,
    "recency": 0.09,
    "tag": 0.10,
    "importance": 0.08,
}
RRF_WEIGHTS_WITH_ACTIVATION = {
    "vector": 0.27,
    "activation": 0.23,
    "entity": 0.14,
    "keyword": 0.14,
    "recency": 0.05,
    "tag": 0.09,
    "importance": 0.08,
}
RRF_WEIGHTS_WITH_GRAPH = {
    "vector": 0.32,
    "graph": 0.18,
    "keyword": 0.14,
    "recency": 0.13,
    "entity": 0.09,
    "tag": 0.06,
    "importance": 0.08,
}
RRF_WEIGHTS_WITH_ACCESS = {
    "vector": 0.41,
    "recency": 0.16,
    "keyword": 0.16,
    "tag": 0.09,
    "access": 0.10,
    "importance": 0.08,
}
RRF_WEIGHTS_WITH_ACCESS_ENTITIES = {
    "vector": 0.32,
    "entity": 0.16,
    "keyword": 0.15,
    "recency": 0.09,
    "tag": 0.10,
    "access": 0.10,
    "importance": 0.08,
}

# Query type affinity map — maps query intent to memory types that are most likely relevant.
QUERY_TYPE_AFFINITY = {
    "factual":     ["note", "learning", "decision", "research"],
    "temporal":    ["progress", "task", "discussion"],
    "procedural":  ["code-snippet", "rule", "design"],
    "exploratory": ["research", "discussion", "learning", "design"],
    "debug":       ["debug", "code-snippet", "learning"],
}

# Type routing boost multiplier — memories matching query-type affinity get this boost.
TYPE_ROUTING_BOOST = 1.3

# Drift detection
MAX_FILE_HASHES = 50                 # max file hashes accepted per store() call


class MemoryAction:
    UPDATE = "update"
    INACTIVATE = "inactivate"
    REACTIVATE = "reactivate"

    ALL = {UPDATE, INACTIVATE, REACTIVATE}


# ============================================================
# Cairns (Episodic) — deprecated in v0.37.0, kept for backward compat
# ============================================================

class CairnAction:
    SET = "set"
    STACK = "stack"
    GET = "get"
    COMPRESS = "compress"

    ALL = {SET, STACK, GET, COMPRESS}


MAX_CAIRN_STACK = 50  # deprecated — kept for backward compat


# ============================================================
# Tasks
# ============================================================

class TaskStatus:
    PENDING = "pending"
    COMPLETED = "completed"


# ============================================================
# Work Items (v0.47.0)
# ============================================================

class WorkItemStatus:
    OPEN = "open"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"

    TRANSITIONS = {
        OPEN: {READY, IN_PROGRESS, BLOCKED, CANCELLED},
        READY: {IN_PROGRESS, BLOCKED, CANCELLED},
        IN_PROGRESS: {DONE, BLOCKED, CANCELLED},
        BLOCKED: {OPEN, READY, IN_PROGRESS, CANCELLED},
        DONE: set(),
        CANCELLED: set(),
    }

    ACTIVE = {OPEN, READY, IN_PROGRESS, BLOCKED}
    TERMINAL = {DONE, CANCELLED}
    ALL = ACTIVE | TERMINAL


class WorkItemType:
    EPIC = "epic"
    TASK = "task"
    SUBTASK = "subtask"

    ALL = {EPIC, TASK, SUBTASK}

    # Auto-infer child type from parent
    CHILD_TYPE = {
        EPIC: TASK,
        TASK: SUBTASK,
        SUBTASK: SUBTASK,
    }


DEFAULT_PREFIX_LENGTH = 2
MIN_PREFIX_LENGTH = 1
MAX_PREFIX_LENGTH = 10


class GateType:
    HUMAN = "human"
    TIMER = "timer"
    ALL = {HUMAN, TIMER}


class RiskTier:
    PATROL = 0       # Just do it
    CAUTION = 1      # Review recommended
    ACTION = 2       # Requires review
    CRITICAL = 3     # Human must confirm
    ALL = {0, 1, 2, 3}
    LABELS = {0: "patrol", 1: "caution", 2: "action", 3: "critical"}


class AgentState:
    WORKING = "working"
    STUCK = "stuck"
    DONE = "done"
    ALL = {WORKING, STUCK, DONE}


class ActivityType:
    STATUS_CHANGE = "status_change"
    CLAIM = "claim"
    GATE_SET = "gate_set"
    GATE_RESOLVED = "gate_resolved"
    HEARTBEAT = "heartbeat"
    CHECKPOINT = "checkpoint"
    NOTE = "note"
    CREATED = "created"
    PROMOTED = "promoted"
    DISPATCHED = "dispatched"
    DELIVERABLE = "deliverable"
    REVIEW = "review"
    ALL = {STATUS_CHANGE, CLAIM, GATE_SET, GATE_RESOLVED, HEARTBEAT, CHECKPOINT, NOTE, CREATED, PROMOTED, DISPATCHED, DELIVERABLE, REVIEW}


class DeliverableStatus:
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REVISED = "revised"
    REJECTED = "rejected"

    REVIEWABLE = {DRAFT, PENDING_REVIEW}
    TERMINAL = {APPROVED, REVISED, REJECTED}
    ALL = REVIEWABLE | TERMINAL


# ============================================================
# Thinking Sequences
# ============================================================

class ThinkingStatus:
    ACTIVE = "active"
    COMPLETED = "completed"


VALID_THOUGHT_TYPES = [
    "observation", "hypothesis", "question", "reasoning", "conclusion",
    "assumption", "analysis", "general", "alternative", "branch",
    "insight", "realization", "pattern", "challenge", "response",
    # Coordinator deliberation types (ca-102)
    "tradeoff", "decision", "risk", "dependency", "scope",
]


# ============================================================
# Projects
# ============================================================

VALID_DOC_TYPES = ["brief", "prd", "plan", "primer", "writeup", "guide", "architecture"]
VALID_LINK_TYPES = ["related", "parent", "child", "dependency", "fork", "template"]


# ============================================================
# Event Pipeline
# ============================================================

# Event Bus (v0.50.0)
EVENT_STREAM_HEARTBEAT_INTERVAL = 15  # seconds between SSE heartbeats


# ============================================================
# Context Budget (token limits for MCP tool responses)
# ============================================================

# Per-tool response budgets (tokens). 0 = disabled (no limit).
BUDGET_RULES = 3000
BUDGET_SEARCH = 4000
BUDGET_RECALL = 8000
BUDGET_CAIRN_STACK = 3000
BUDGET_INSIGHTS = 4000
BUDGET_WORKSPACE = 6000
BUDGET_ORIENT = 6000

# Orient() section allocation (percentage of total orient budget)
ORIENT_ALLOC_RULES = 0.27
ORIENT_ALLOC_LEARNINGS = 0.22
ORIENT_ALLOC_TRAIL = 0.23
ORIENT_ALLOC_WORKING_MEMORY = 0.10
ORIENT_ALLOC_WORK_ITEMS = 0.18

# Handler dispatch confidence threshold (SearchV2)
HANDLER_CONFIDENCE_THRESHOLD = 0.6

# Per-item content truncation limits (tokens)
BUDGET_RULES_PER_ITEM = 300
BUDGET_SEARCH_PER_ITEM = 200
BUDGET_RECALL_PER_ITEM = 2000
BUDGET_CAIRN_NARRATIVE_CHARS = 300
BUDGET_INSIGHTS_PER_ITEM = 300

# Workspace context allocation (percentage of total budget)
WORKSPACE_ALLOC_RULES = 0.35
WORKSPACE_ALLOC_MEMORIES = 0.30
WORKSPACE_ALLOC_TRAIL = 0.20
WORKSPACE_ALLOC_TASKS = 0.15
