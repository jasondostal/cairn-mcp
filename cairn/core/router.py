"""Query intent classification for search_v2.

Single LLM call classifies query into one of 5 types and extracts
entity hints, aspects, and temporal constraints for handler dispatch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator

from cairn.core.utils import extract_json

if TYPE_CHECKING:
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

VALID_QUERY_TYPES = {
    "aspect_query", "entity_lookup", "temporal", "exploratory", "relationship",
}

VALID_ASPECTS = {
    "Identity", "Knowledge", "Belief", "Preference", "Action",
    "Goal", "Directive", "Decision", "Event", "Problem", "Relationship",
}


ROUTER_SYSTEM_PROMPT = """\
You classify search queries for a project-scoped memory system. The system stores memories about projects, decisions, infrastructure, and work.

## Query Types

**entity_lookup** — Query names a specific person, project, technology, or thing and wants info about it.
- "Who is Sarah?" "What is Cairn?" "Tell me about Redis"

**aspect_query** — Query asks about a specific KIND of information about an entity or topic.
- "What are Alice's preferences?" → entity_hints=["Alice"], aspects=["Preference"]
- "What decisions were made about the database?" → entity_hints=["database"], aspects=["Decision"]
- "What problems have we had with deployment?" → entity_hints=["deployment"], aspects=["Problem"]

**temporal** — Query is primarily about WHEN something happened or asks for recent activity.
- "What happened last week?" "Recent changes" "What did we do yesterday?"
- NOT temporal just because it mentions a date in passing

**relationship** — Query asks about connections BETWEEN two or more entities.
- "How are Alice and the DevOps team related?" "What's the connection between Cairn and Neo4j?"
- Requires 2+ entity_hints to be useful

**exploratory** — Broad, vague, or topic-oriented. Doesn't fit above categories.
- "How does deployment work?" "What do we know about testing?" "Search for memory-related stuff"

## Aspect Definitions (for aspect_query)
- **Identity**: Who/what something IS (name, role, type, origin, description)
- **Knowledge**: Facts someone knows or learned
- **Belief**: Opinions, worldview, what someone thinks is true
- **Preference**: Likes, dislikes, favorites, choices
- **Action**: What someone did or does regularly
- **Goal**: Aspirations, plans, intentions
- **Directive**: Rules, instructions, guidelines to follow
- **Decision**: Choices made with reasoning
- **Event**: Things that happened at a specific time
- **Problem**: Issues, bugs, blockers, failures
- **Relationship**: Connections between people/things

## Entity Hints
Extract ALL named entities in the query — people, projects, technologies, places, organizations. Be generous. "What did we deploy to production last week?" → ["production"]. "How is Alice's Cairn project going?" → ["Alice", "Cairn"].

## Rules
1. If the query mentions a specific entity AND asks about a property/aspect, prefer **aspect_query** over entity_lookup
2. If the query is about what happened in a time period, use **temporal** even if entities are mentioned
3. **exploratory** is the fallback — only use it when nothing else fits
4. Always extract entity_hints even for non-entity query types
5. Set confidence low (<0.5) if you're unsure about the classification

## Examples

Query: "What database does the project use?"
→ {"query_type": "aspect_query", "aspects": ["Identity"], "entity_hints": ["database"], "temporal": {"after": null, "before": null}, "confidence": 0.9}

Query: "Who is Alice?"
→ {"query_type": "entity_lookup", "aspects": ["Identity"], "entity_hints": ["Alice"], "temporal": {"after": null, "before": null}, "confidence": 0.95}

Query: "What happened during the deploy last week?"
→ {"query_type": "temporal", "aspects": ["Event"], "entity_hints": ["deploy"], "temporal": {"after": "last week", "before": null}, "confidence": 0.85}

Query: "How are Alice and the DevOps team connected?"
→ {"query_type": "relationship", "aspects": ["Relationship"], "entity_hints": ["Alice", "DevOps team"], "temporal": {"after": null, "before": null}, "confidence": 0.9}

Query: "What do we know about caching?"
→ {"query_type": "exploratory", "aspects": [], "entity_hints": ["caching"], "temporal": {"after": null, "before": null}, "confidence": 0.7}

Query: "What decisions were made about the API?"
→ {"query_type": "aspect_query", "aspects": ["Decision"], "entity_hints": ["API"], "temporal": {"after": null, "before": null}, "confidence": 0.85}

Return ONLY the JSON object."""


class TemporalFilter(BaseModel):
    after: str | None = None
    before: str | None = None


class RouterOutput(BaseModel):
    query_type: str = "exploratory"
    aspects: list[str] = []
    entity_hints: list[str] = []
    temporal: TemporalFilter = TemporalFilter()
    confidence: float = 0.5

    @field_validator("query_type")
    @classmethod
    def validate_query_type(cls, v: str) -> str:
        if v not in VALID_QUERY_TYPES:
            for qt in VALID_QUERY_TYPES:
                if v.lower() == qt.lower():
                    return qt
            return "exploratory"
        return v

    @field_validator("aspects")
    @classmethod
    def validate_aspects(cls, v: list[str]) -> list[str]:
        return [a for a in v if a in VALID_ASPECTS]

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class QueryRouter:
    """Classify query intent for handler dispatch."""

    def __init__(self, llm: LLMInterface):
        self.llm = llm

    def route(self, query: str) -> RouterOutput:
        """Classify query and extract routing metadata.

        On any failure, returns default exploratory route.
        """
        try:
            messages = [
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ]
            raw = self.llm.generate(messages, max_tokens=512)
            data = extract_json(raw, json_type="object")
            if data is None:
                logger.warning("Router: no JSON in response")
                return RouterOutput()
            result = RouterOutput(**data)
            logger.debug("Routed query to %s (confidence=%.2f)", result.query_type, result.confidence)
            return result
        except Exception:
            logger.warning("Query routing failed, defaulting to exploratory", exc_info=True)
            return RouterOutput()
