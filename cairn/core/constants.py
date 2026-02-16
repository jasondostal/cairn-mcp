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

# Input limits
MAX_CONTENT_SIZE = 100_000  # ~100KB
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
    "vector": 0.50,
    "recency": 0.20,
    "keyword": 0.20,
    "tag": 0.10,
}
RRF_WEIGHTS_WITH_ENTITIES = {
    "vector": 0.40,
    "entity": 0.20,
    "keyword": 0.20,
    "recency": 0.10,
    "tag": 0.10,
}
RRF_WEIGHTS_WITH_ACTIVATION = {
    "vector": 0.30,
    "activation": 0.25,
    "entity": 0.15,
    "keyword": 0.15,
    "recency": 0.05,
    "tag": 0.10,
}
RRF_WEIGHTS_WITH_GRAPH = {
    "vector": 0.35,
    "graph": 0.20,
    "keyword": 0.15,
    "recency": 0.15,
    "entity": 0.10,
    "tag": 0.05,
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
# Thinking Sequences
# ============================================================

class ThinkingStatus:
    ACTIVE = "active"
    COMPLETED = "completed"


VALID_THOUGHT_TYPES = [
    "observation", "hypothesis", "question", "reasoning", "conclusion",
    "assumption", "analysis", "general", "alternative", "branch",
]


# ============================================================
# Projects
# ============================================================

VALID_DOC_TYPES = ["brief", "prd", "plan", "primer", "writeup", "guide"]
VALID_LINK_TYPES = ["related", "parent", "child", "dependency", "fork", "template"]


# ============================================================
# Event Pipeline
# ============================================================

EVENT_BATCH_SIZE = 25              # default events per batch shipped by hooks
MAX_EVENT_BATCH_SIZE = 200         # max events accepted in a single ingest call
DIGEST_POLL_INTERVAL = 5.0         # seconds between DigestWorker poll cycles
DIGEST_MAX_EVENTS_PER_BATCH = 50   # max events sent to LLM for a single digest


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
ORIENT_ALLOC_RULES = 0.30
ORIENT_ALLOC_LEARNINGS = 0.25
ORIENT_ALLOC_TRAIL = 0.25
ORIENT_ALLOC_TASKS = 0.20

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
