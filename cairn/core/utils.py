"""Shared utilities for Cairn core modules. DRY helpers."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when MCP tool input fails validation."""


def validate_store(content, project, memory_type, importance, tags, session_name):
    """Validate store tool inputs. Raises ValidationError on bad input."""
    from cairn.core.constants import (
        MAX_CONTENT_SIZE, MAX_NAME_LENGTH, MAX_TAGS, MAX_TAG_LENGTH,
        VALID_MEMORY_TYPES,
    )
    if not content or not content.strip():
        raise ValidationError("content is required and cannot be empty")
    if len(content) > MAX_CONTENT_SIZE:
        raise ValidationError(f"content exceeds {MAX_CONTENT_SIZE} character limit")
    if not project or not project.strip():
        raise ValidationError("project is required")
    if len(project) > MAX_NAME_LENGTH:
        raise ValidationError(f"project name exceeds {MAX_NAME_LENGTH} character limit")
    if memory_type and memory_type not in VALID_MEMORY_TYPES:
        raise ValidationError(f"invalid memory_type: {memory_type}. Must be one of: {', '.join(VALID_MEMORY_TYPES)}")
    if importance is not None and not (0.0 <= importance <= 1.0):
        raise ValidationError("importance must be between 0.0 and 1.0")
    if tags:
        if len(tags) > MAX_TAGS:
            raise ValidationError(f"maximum {MAX_TAGS} tags allowed")
        for t in tags:
            if len(str(t)) > MAX_TAG_LENGTH:
                raise ValidationError(f"tag exceeds {MAX_TAG_LENGTH} character limit")
    if session_name and len(session_name) > MAX_NAME_LENGTH:
        raise ValidationError(f"session_name exceeds {MAX_NAME_LENGTH} character limit")


def validate_search(query, limit):
    """Validate search tool inputs."""
    from cairn.core.constants import MAX_SEARCH_QUERY, MAX_LIMIT
    if not query or not query.strip():
        raise ValidationError("query is required")
    if len(query) > MAX_SEARCH_QUERY:
        raise ValidationError(f"query exceeds {MAX_SEARCH_QUERY} character limit")
    if limit is not None and limit > MAX_LIMIT:
        raise ValidationError(f"limit cannot exceed {MAX_LIMIT}")


def get_project(db: Database, project_name: str) -> int | None:
    """Resolve project name to ID. Returns project ID or None if not found."""
    row = db.execute_one(
        "SELECT id FROM projects WHERE name = %s", (project_name,)
    )
    return row["id"] if row else None


def get_or_create_project(db: Database, project_name: str) -> int:
    """Resolve project name to ID, creating if needed. Returns project ID.

    Use this only on write paths (store, create, set). For read paths,
    use get_project() to avoid creating phantom projects from typos.
    """
    project_id = get_project(db, project_name)
    if project_id is not None:
        return project_id

    row = db.execute_one(
        "INSERT INTO projects (name) VALUES (%s) RETURNING id",
        (project_name,),
    )
    db.commit()
    return row["id"]


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM response text."""
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text


def extract_json(raw: str, json_type: str = "object") -> dict | list | None:
    """Extract JSON from an LLM response, handling markdown fences and nested objects.

    Args:
        raw: Raw LLM response string.
        json_type: "object" to extract {...} or "array" to extract [...].

    Returns:
        Parsed JSON (dict or list), or None if extraction fails.
    """
    text = strip_markdown_fences(raw.strip())

    # Fast path: try parsing the whole text directly
    try:
        result = json.loads(text)
        if json_type == "object" and isinstance(result, dict):
            return result
        if json_type == "array" and isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Slow path: find outermost matching braces/brackets
    open_char = "{" if json_type == "object" else "["
    close_char = "}" if json_type == "object" else "]"

    start = text.find(open_char)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == open_char:
            depth += 1
        elif c == close_char:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None

    return None
