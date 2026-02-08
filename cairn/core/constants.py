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


class MemoryAction:
    UPDATE = "update"
    INACTIVATE = "inactivate"
    REACTIVATE = "reactivate"

    ALL = {UPDATE, INACTIVATE, REACTIVATE}


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

VALID_DOC_TYPES = ["brief", "prd", "plan"]
VALID_LINK_TYPES = ["related", "parent", "child", "dependency", "fork", "template"]
