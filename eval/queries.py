"""Query and relevance judgment loading.

Loads queries.json — each query has an ID, text, expected relevant memory IDs,
optional filters, and notes.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"


@dataclass
class Query:
    """A single evaluation query with relevance judgments."""
    id: str
    query: str
    relevant: set[str]
    filters: dict = field(default_factory=dict)
    notes: str = ""


def load_queries(path: Path | None = None) -> list[Query]:
    """Load and validate queries.json.

    Returns list of Query objects.
    Raises ValueError on schema violations.
    """
    path = path or DATA_DIR / "queries.json"
    if not path.exists():
        raise FileNotFoundError(f"Queries file not found: {path}")

    data = json.loads(path.read_text())

    if "queries" not in data:
        raise ValueError("Queries file must contain 'queries' key")
    if not data["queries"]:
        raise ValueError("Queries file must contain at least one query")

    queries = []
    ids_seen = set()
    for q in data["queries"]:
        if "id" not in q or "query" not in q or "relevant" not in q:
            raise ValueError(f"Query missing required fields: {q}")
        if q["id"] in ids_seen:
            raise ValueError(f"Duplicate query ID: {q['id']}")
        ids_seen.add(q["id"])

        if not q["relevant"]:
            raise ValueError(f"Query {q['id']} has no relevant memories")

        queries.append(Query(
            id=q["id"],
            query=q["query"],
            relevant=set(q["relevant"]),
            filters=q.get("filters", {}),
            notes=q.get("notes", ""),
        ))

    logger.info("Loaded %d queries", len(queries))
    return queries
