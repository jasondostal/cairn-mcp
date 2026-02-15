"""Combined knowledge extraction + enrichment.

Single LLM call extracts entities, statements (with triples), tags, importance,
and summary. Replaces separate Enricher when knowledge_extraction is enabled.

On parse failure: retry once with error feedback. On second failure: fall back
to returning only basic enrichment fields from the raw content.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator

from cairn.core.constants import VALID_MEMORY_TYPES
from cairn.core.extraction_prompt import build_extraction_messages, build_extraction_retry_messages
from cairn.core.utils import extract_json

if TYPE_CHECKING:
    from cairn.embedding.interface import EmbeddingInterface
    from cairn.graph.interface import GraphProvider
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

# Valid aspect values
VALID_ASPECTS = {
    "Identity", "Knowledge", "Belief", "Preference", "Action",
    "Goal", "Directive", "Decision", "Event", "Problem", "Relationship",
}

# Aspects where same subject+predicate means contradiction.
# Event/Action/Knowledge accumulate — they don't contradict.
CONTRADICTING_ASPECTS = {"Identity", "Preference", "Belief", "Directive"}

VALID_ENTITY_TYPES = {
    "Person", "Organization", "Place", "Event", "Project",
    "Task", "Technology", "Product", "Concept",
}


class ExtractedEntity(BaseModel):
    name: str
    entity_type: str
    attributes: dict[str, str] = {}

    @field_validator("entity_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_ENTITY_TYPES:
            # Attempt case-insensitive match
            for t in VALID_ENTITY_TYPES:
                if v.lower() == t.lower():
                    return t
            raise ValueError(f"Invalid entity type: {v}")
        return v


class ExtractedStatement(BaseModel):
    subject: str
    predicate: str
    object: str
    fact: str
    aspect: str
    event_date: str | None = None

    @field_validator("aspect")
    @classmethod
    def validate_aspect(cls, v: str) -> str:
        if v not in VALID_ASPECTS:
            for a in VALID_ASPECTS:
                if v.lower() == a.lower():
                    return a
            raise ValueError(f"Invalid aspect: {v}")
        return v

    @field_validator("fact")
    @classmethod
    def validate_fact_length(cls, v: str) -> str:
        # Soft limit — truncate rather than reject
        words = v.split()
        if len(words) > 20:
            return " ".join(words[:20])
        return v


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = []
    statements: list[ExtractedStatement] = []
    tags: list[str] = []
    importance: float = 0.5
    summary: str = ""

    @field_validator("importance")
    @classmethod
    def clamp_importance(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: list[str]) -> list[str]:
        return [t.lower().strip() for t in v if t][:10]


class KnowledgeExtractor:
    """Combined extraction + enrichment via single LLM call.

    Extracts entities, statements, tags, importance, and summary.
    Persists entities and statements to the knowledge graph.
    """

    def __init__(
        self,
        llm: LLMInterface,
        embedding: EmbeddingInterface,
        graph: GraphProvider,
    ):
        self.llm = llm
        self.embedding = embedding
        self.graph = graph
        self._embed_cache: dict[str, list[float]] = {}
        self._cache_lock = threading.Lock()

    def _cached_embed(self, text: str) -> list[float]:
        """Embed with thread-safe cache. Saves redundant API calls for repeated entity names."""
        with self._cache_lock:
            cached = self._embed_cache.get(text)
        if cached is not None:
            return cached
        vec = self.embedding.embed(text)
        with self._cache_lock:
            self._embed_cache[text] = vec
        return vec

    def extract(
        self, content: str, created_at: str | None = None, author: str | None = None,
        known_entities: list[dict] | None = None,
    ) -> ExtractionResult | None:
        """Run extraction LLM call and parse result.

        Args:
            content: Memory text to extract from.
            created_at: ISO timestamp for resolving relative dates.
            author: Voice attribution ("user", "assistant", "collaborative").
            known_entities: Existing entity names/types for canonicalization.

        Returns ExtractionResult on success, None on total failure.
        Retries once on parse failure.
        """
        try:
            messages = build_extraction_messages(
                content, created_at=created_at, author=author,
                known_entities=known_entities,
            )
            raw = self.llm.generate(messages, max_tokens=2048)
            return self._parse(raw)
        except Exception as first_error:
            logger.warning("Extraction first attempt failed: %s", first_error)
            try:
                messages = build_extraction_retry_messages(content, str(first_error))
                raw = self.llm.generate(messages, max_tokens=2048)
                return self._parse(raw)
            except Exception:
                logger.warning("Extraction retry failed, returning None", exc_info=True)
                return None

    def _parse(self, raw: str) -> ExtractionResult:
        """Parse LLM JSON response into validated ExtractionResult."""
        data = extract_json(raw, json_type="object")
        if data is None:
            raise ValueError(f"No JSON object found in response: {raw[:200]}")
        return ExtractionResult(**data)

    def resolve_and_persist(
        self,
        result: ExtractionResult,
        episode_id: int,
        project_id: int,
    ) -> dict:
        """Resolve entities, detect contradictions, and persist to graph.

        Returns summary dict with counts of created/merged entities and statements.
        """
        # Step 1: Resolve entities — embed name, find similar, merge or create
        entity_map: dict[str, str] = {}  # entity name -> UUID
        entities_created = 0
        entities_merged = 0

        for entity in result.entities:
            try:
                name_embedding = self._cached_embed(entity.name)

                # Try type-scoped match first (0.85 threshold)
                similar = self.graph.find_similar_entities(
                    name_embedding, entity.entity_type, project_id,
                )
                if similar:
                    entity_map[entity.name] = similar[0].uuid
                    entities_merged += 1
                    logger.debug("Entity merged (type-scoped): %s -> %s", entity.name, similar[0].uuid)
                    continue

                # Fallback: type-agnostic match (0.95 threshold — stricter)
                similar_any = self.graph.find_similar_entities_any_type(
                    name_embedding, project_id, threshold=0.95,
                )
                if similar_any:
                    entity_map[entity.name] = similar_any[0].uuid
                    entities_merged += 1
                    logger.debug(
                        "Entity merged (type-agnostic): %s (%s) -> %s (%s)",
                        entity.name, entity.entity_type,
                        similar_any[0].name, similar_any[0].entity_type,
                    )
                    continue

                # Create new entity
                uuid = self.graph.create_entity(
                    name=entity.name,
                    entity_type=entity.entity_type,
                    embedding=name_embedding,
                    project_id=project_id,
                    attributes=entity.attributes,
                )
                entity_map[entity.name] = uuid
                entities_created += 1
            except Exception:
                logger.warning("Entity resolution failed for %s", entity.name, exc_info=True)

        # Step 2: Create statements with contradiction detection
        statements_created = 0
        contradictions_found = 0

        for stmt in result.statements:
            try:
                subject_uuid = entity_map.get(stmt.subject)
                if not subject_uuid:
                    # Subject not in our entity map — skip this statement
                    logger.debug("Skipping statement, subject not found: %s", stmt.subject)
                    continue

                # Check for contradictions (same subject + predicate)
                # Only flag contradictions within Identity, Preference, Belief,
                # Directive aspects. Event/Action/Knowledge accumulate.
                existing = self.graph.find_contradictions(
                    subject_uuid, stmt.predicate, project_id,
                )
                for old_stmt in existing:
                    # Skip if the old statement's aspect isn't in contradicting set
                    if old_stmt.aspect not in CONTRADICTING_ASPECTS:
                        continue
                    # Skip if both have valid_at dates and they differ (temporal evolution)
                    if (old_stmt.valid_at and stmt.event_date
                            and old_stmt.valid_at != stmt.event_date):
                        continue
                    self.graph.invalidate_statement(old_stmt.uuid, invalidated_by="extraction")
                    contradictions_found += 1

                # Create the new statement
                fact_embedding = self._cached_embed(stmt.fact)
                stmt_uuid = self.graph.create_statement(
                    fact=stmt.fact,
                    embedding=fact_embedding,
                    aspect=stmt.aspect,
                    episode_id=episode_id,
                    project_id=project_id,
                    valid_at=stmt.event_date,
                )

                # Resolve object — could be entity name or literal
                object_uuid = entity_map.get(stmt.object)
                self.graph.create_triple(
                    statement_id=stmt_uuid,
                    subject_id=subject_uuid,
                    predicate=stmt.predicate,
                    object_id=object_uuid,
                    object_value=stmt.object if not object_uuid else None,
                )
                statements_created += 1

            except Exception:
                logger.warning("Statement creation failed: %s", stmt.fact, exc_info=True)

        return {
            "entities_created": entities_created,
            "entities_merged": entities_merged,
            "statements_created": statements_created,
            "contradictions_found": contradictions_found,
        }

    def resolve_dangling_objects(self, project_id: int) -> int:
        """Post-extraction pass: resolve string object_value against known entities.

        For each statement with a string object_value, embed it and search for
        matching entities. If a match is found (>0.90), link the entity and clear
        the string value.

        Returns count of resolved objects.
        """
        resolved = 0
        try:
            dangling = self.graph.find_dangling_objects(project_id)
            if not dangling:
                return 0

            for stmt in dangling:
                try:
                    obj_embedding = self._cached_embed(stmt["object_value"])
                    matches = self.graph.find_similar_entities_any_type(
                        obj_embedding, project_id, threshold=0.90,
                    )
                    if matches:
                        self.graph.link_object_entity(stmt["uuid"], matches[0].uuid)
                        resolved += 1
                        logger.debug(
                            "Resolved dangling object: '%s' -> entity %s",
                            stmt["object_value"], matches[0].name,
                        )
                except Exception:
                    logger.debug("Failed to resolve object '%s'", stmt["object_value"], exc_info=True)

        except Exception:
            logger.warning("Dangling object resolution failed", exc_info=True)

        if resolved > 0:
            logger.info("Resolved %d dangling objects (project_id=%d)", resolved, project_id)
        return resolved

    def extract_enrichment_fields(self, result: ExtractionResult) -> dict:
        """Extract enrichment-compatible fields from ExtractionResult.

        Returns dict compatible with the existing enrichment pipeline
        (tags, importance, summary, entities, memory_type).
        """
        # Derive entity names for the legacy entities field
        entity_names = [e.name for e in result.entities]

        return {
            "tags": result.tags,
            "importance": result.importance,
            "summary": result.summary,
            "entities": entity_names,
        }
