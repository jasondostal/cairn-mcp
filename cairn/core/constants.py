"""Centralized constants and enums for Cairn core modules."""

from __future__ import annotations

# ============================================================
# Memory
# ============================================================

VALID_MEMORY_TYPES = [
    "note", "decision", "rule", "code-snippet", "learning",
    "research", "discussion", "progress", "task", "debug", "design",
    # Ephemeral types (formerly working memory) — stored with salience, decay over time
    "hypothesis", "question", "tension", "connection", "thread", "intuition",
]

# Ephemeral memory types — these get auto-salience when stored without explicit salience
EPHEMERAL_MEMORY_TYPES = {"hypothesis", "question", "tension", "connection", "thread", "intuition"}

# Graduation: ephemeral type -> crystallized type (used by modify action='graduate')
GRADUATION_TYPE_MAP = {
    "hypothesis": "learning",
    "question": "note",
    "tension": "decision",
    "connection": "note",
    "thread": "progress",
    "intuition": "learning",
}

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

# Document attachments
ALLOWED_ATTACHMENT_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
}
MAX_ATTACHMENT_SIZE = 10_000_000  # 10MB
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
    GRADUATE = "graduate"
    PIN = "pin"
    UNPIN = "unpin"
    BOOST = "boost"

    ALL = {UPDATE, INACTIVATE, REACTIVATE, GRADUATE, PIN, UNPIN, BOOST}


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


class EventType:
    """Canonical event type registry — all event types used across the system.

    Replaces stringly-typed event types scattered across publishers/subscribers.
    Each constant includes its category for MetricsCollector mapping.
    """

    # Memory events
    MEMORY_CREATED = "memory.created"
    MEMORY_UPDATED = "memory.updated"
    MEMORY_INACTIVATED = "memory.inactivated"
    MEMORY_REACTIVATED = "memory.reactivated"
    MEMORY_GRADUATED = "memory.graduated"
    MEMORY_BOOSTED = "memory.boosted"
    MEMORY_CONSOLIDATED = "memory.consolidated"
    MEMORY_RECALLED = "memory.recalled"

    # Search events
    SEARCH_EXECUTED = "search.executed"

    # Work item events
    WORK_ITEM_CREATED = "work_item.created"
    WORK_ITEM_UPDATED = "work_item.updated"
    WORK_ITEM_STATUS_CHANGED = "work_item.status_changed"
    WORK_ITEM_CLAIMED = "work_item.claimed"
    WORK_ITEM_COMPLETED = "work_item.completed"
    WORK_ITEM_BLOCKED = "work_item.blocked"
    WORK_ITEM_UNBLOCKED = "work_item.unblocked"
    WORK_ITEM_GATE_SET = "work_item.gate_set"
    WORK_ITEM_GATE_RESOLVED = "work_item.gate_resolved"
    WORK_ITEM_MEMORIES_LINKED = "work_item.memories_linked"

    # Deliverable events
    DELIVERABLE_CREATED = "deliverable.created"
    DELIVERABLE_SUBMITTED = "deliverable.submitted"
    DELIVERABLE_APPROVED = "deliverable.approved"
    DELIVERABLE_REVISED = "deliverable.revised"
    DELIVERABLE_REJECTED = "deliverable.rejected"

    # Belief events
    BELIEF_CRYSTALLIZED = "belief.crystallized"
    BELIEF_CHALLENGED = "belief.challenged"
    BELIEF_RETRACTED = "belief.retracted"
    BELIEF_SUPERSEDED = "belief.superseded"

    # Working memory events
    WM_CAPTURED = "working_memory.captured"
    WM_RESOLVED = "working_memory.resolved"
    WM_GRADUATED = "working_memory.graduated"
    WM_BOOSTED = "working_memory.boosted"
    WM_ARCHIVED = "working_memory.archived"

    # Thinking events
    THINKING_STARTED = "thinking.sequence_started"
    THINKING_THOUGHT_ADDED = "thinking.thought_added"
    THINKING_CONCLUDED = "thinking.sequence_concluded"
    THINKING_REOPENED = "thinking.sequence_reopened"

    # Settings events
    SETTINGS_UPDATED = "settings.updated"
    SETTINGS_DELETED = "settings.deleted"

    # Session events
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # Category mapping for MetricsCollector
    CATEGORIES = {
        "memory.created": "writes", "memory.updated": "writes",
        "memory.inactivated": "writes", "memory.reactivated": "writes",
        "memory.graduated": "writes", "memory.boosted": "writes",
        "memory.consolidated": "writes", "memory.recalled": "reads",
        "search.executed": "reads",
        "work_item.created": "work", "work_item.updated": "work",
        "work_item.status_changed": "work", "work_item.claimed": "work",
        "work_item.completed": "work", "work_item.blocked": "work",
        "work_item.unblocked": "work", "work_item.gate_set": "work",
        "work_item.gate_resolved": "work", "work_item.memories_linked": "work",
        "deliverable.created": "work", "deliverable.submitted": "work",
        "deliverable.approved": "work", "deliverable.revised": "work",
        "deliverable.rejected": "work",
        "belief.crystallized": "writes", "belief.challenged": "writes",
        "belief.retracted": "writes", "belief.superseded": "writes",
        "working_memory.captured": "writes", "working_memory.resolved": "system",
        "working_memory.graduated": "writes", "working_memory.boosted": "writes",
        "working_memory.archived": "system",
        "thinking.sequence_started": "llm", "thinking.thought_added": "llm",
        "thinking.sequence_concluded": "llm", "thinking.sequence_reopened": "llm",
        "settings.updated": "system", "settings.deleted": "system",
        "session_start": "sessions", "session_end": "sessions",
    }

    # Prefix-based fallback for dynamic/tool event types
    PREFIX_CATEGORIES = {
        "memory.": "writes",
        "search.": "reads",
        "work_item.": "work",
        "deliverable.": "work",
        "belief.": "writes",
        "working_memory.": "system",
        "thinking.": "llm",
        "settings.": "system",
        "tool.": "other",
    }

    @classmethod
    def category_for(cls, event_type: str) -> str:
        """Get the metrics category for an event type."""
        cat = cls.CATEGORIES.get(event_type)
        if cat:
            return cat
        for prefix, category in cls.PREFIX_CATEGORIES.items():
            if event_type.startswith(prefix):
                return category
        return "other"


# Event Bus (v0.50.0)
EVENT_STREAM_HEARTBEAT_INTERVAL = 15  # seconds between SSE heartbeats


# ============================================================
# Context Budget (token limits for MCP tool responses)
# ============================================================

# Per-tool response budgets (tokens). 0 = disabled (no limit).
BUDGET_RULES = 3000
BUDGET_SEARCH = 4000
BUDGET_RECALL = 8000
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
BUDGET_INSIGHTS_PER_ITEM = 300

# Workspace context allocation (percentage of total budget)
WORKSPACE_ALLOC_RULES = 0.35
WORKSPACE_ALLOC_MEMORIES = 0.30
WORKSPACE_ALLOC_TRAIL = 0.20
WORKSPACE_ALLOC_TASKS = 0.15
