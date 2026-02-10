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


class MemoryAction:
    UPDATE = "update"
    INACTIVATE = "inactivate"
    REACTIVATE = "reactivate"

    ALL = {UPDATE, INACTIVATE, REACTIVATE}


# ============================================================
# Cairns (Episodic)
# ============================================================

class CairnAction:
    SET = "set"
    STACK = "stack"
    GET = "get"
    COMPRESS = "compress"

    ALL = {SET, STACK, GET, COMPRESS}


MAX_CAIRN_STACK = 50  # max cairns returned by stack


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
