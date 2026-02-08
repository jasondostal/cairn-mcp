"""Shared utilities for Cairn core modules. DRY helpers."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


def get_or_create_project(db: Database, project_name: str) -> int:
    """Resolve project name to ID, creating if needed. Returns project ID."""
    row = db.execute_one(
        "SELECT id FROM projects WHERE name = %s", (project_name,)
    )
    if row:
        return row["id"]

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
    """Extract JSON from an LLM response, handling markdown fences.

    Args:
        raw: Raw LLM response string.
        json_type: "object" to extract {...} or "array" to extract [...].

    Returns:
        Parsed JSON (dict or list), or None if extraction fails.
    """
    text = strip_markdown_fences(raw.strip())

    pattern = r"\{[^{}]*\}" if json_type == "object" else r"\[.*\]"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None
