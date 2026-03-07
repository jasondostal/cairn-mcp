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
        MAX_CONTENT_SIZE,
        MAX_NAME_LENGTH,
        MAX_TAG_LENGTH,
        MAX_TAGS,
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
    from cairn.core.constants import MAX_LIMIT, MAX_SEARCH_QUERY
    if not query or not query.strip():
        raise ValidationError("query is required")
    if len(query) > MAX_SEARCH_QUERY:
        raise ValidationError(f"query exceeds {MAX_SEARCH_QUERY} character limit")
    if limit is not None and limit > MAX_LIMIT:
        raise ValidationError(f"limit cannot exceed {MAX_LIMIT}")


def make_display_id(prefix: str, seq_num: int) -> str:
    """Build a display ID from prefix and sequence number: e.g. 'ca-42'."""
    return f"{prefix}-{seq_num}"


def parse_display_id(display_id: str) -> tuple[str, int] | None:
    """Parse a display ID like 'ca-42' into (prefix, seq_num).

    Splits on the last '-' to handle prefixes that contain hyphens.
    Returns None if parsing fails.
    """
    idx = display_id.rfind("-")
    if idx < 1:
        return None
    prefix = display_id[:idx]
    try:
        seq = int(display_id[idx + 1:])
    except ValueError:
        return None
    return (prefix, seq)


def _generate_prefix(db: Database, project_name: str) -> str:
    """Generate a unique work_item_prefix for a project.

    Reads default length from config (via app_settings), tries progressively
    longer substrings on collision, numeric suffix fallback.
    """
    from cairn.core.constants import DEFAULT_PREFIX_LENGTH

    # Try to read configured default from app_settings
    default_len = DEFAULT_PREFIX_LENGTH
    try:
        from cairn.storage import settings_store
        all_settings = settings_store.load_all(db)
        val = all_settings.get("work_items.default_prefix_length")
        if val is not None:
            default_len = int(val)
    except Exception:
        pass

    # Special-case __global__
    if project_name == "__global__":
        base = "gl"
    else:
        base = re.sub(r"[^a-z0-9]", "", project_name.lower())
        if not base:
            base = "p"

    # Try progressively longer prefixes
    for length in range(default_len, len(base) + 1):
        candidate = base[:length]
        row = db.execute_one(
            "SELECT 1 FROM projects WHERE work_item_prefix = %s",
            (candidate,),
        )
        if not row:
            return candidate

    # Numeric suffix fallback
    suffix = 1
    while True:
        candidate = f"{base[:default_len]}{suffix}"
        row = db.execute_one(
            "SELECT 1 FROM projects WHERE work_item_prefix = %s",
            (candidate,),
        )
        if not row:
            return candidate
        suffix += 1


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

    Auto-generates a work_item_prefix on INSERT (collision-safe).
    """
    project_id = get_project(db, project_name)
    if project_id is not None:
        return project_id

    prefix = _generate_prefix(db, project_name)
    row = db.execute_one(
        "INSERT INTO projects (name, work_item_prefix) VALUES (%s, %s) "
        "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
        "RETURNING id",
        (project_name, prefix),
    )
    assert row is not None

    # RBAC: auto-add creator as project owner (ca-124)
    from cairn.core.user import current_user
    user_ctx = current_user()
    if user_ctx is not None:
        db.execute(
            """
            INSERT INTO user_projects (user_id, project_id, role)
            VALUES (%s, %s, 'owner')
            ON CONFLICT (user_id, project_id) DO NOTHING
            """,
            (user_ctx.user_id, row["id"]),
        )

    db.commit()
    return row["id"]


def parse_vector(text: str | None) -> list[float] | None:
    """Parse a pgvector string like '[0.1,0.2,...]' into a list of floats.

    Handles both string representations and already-parsed sequences.
    Returns None if input is None (no embedding stored).
    """
    if text is None:
        return None
    if isinstance(text, str):
        return [float(x) for x in text.strip("[]").split(",")]
    return list(text)


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


def validate_url(url: str) -> None:
    """Validate a URL for safety. Blocks SSRF vectors.

    Rejects private/reserved IPs, metadata endpoints, loopback,
    and non-http(s) schemes. Used by ingest and webhooks.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs allowed, got: {parsed.scheme}")

    if not parsed.hostname:
        raise ValueError("URL must include a hostname")

    blocked_hosts = {
        "localhost", "127.0.0.1", "0.0.0.0",
        "169.254.169.254", "[::1]",
        "metadata.google.internal",
    }
    if parsed.hostname.lower() in blocked_hosts:
        raise ValueError(f"Fetching from {parsed.hostname} is not allowed")

    try:
        resolved = socket.getaddrinfo(
            parsed.hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM,
        )
        for _, _, _, _, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
                raise ValueError(
                    f"Fetching from private/reserved IP ({ip}) is not allowed"
                )
    except socket.gaierror:
        pass
