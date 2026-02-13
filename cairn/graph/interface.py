"""Graph provider ABC. All graph backends implement this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Entity:
    """An entity node in the knowledge graph."""
    uuid: str
    name: str
    entity_type: str
    project_id: int
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class Statement:
    """A statement (fact) in the knowledge graph."""
    uuid: str
    fact: str
    aspect: str
    episode_id: int
    project_id: int
    valid_at: str | None = None
    invalid_at: str | None = None
    invalidated_by: str | None = None


class GraphProvider(ABC):
    """Abstract base for knowledge graph backends."""

    @abstractmethod
    def connect(self) -> None:
        """Open connection to the graph database."""

    @abstractmethod
    def close(self) -> None:
        """Close connection to the graph database."""

    @abstractmethod
    def ensure_schema(self) -> None:
        """Create constraints, indexes, and schema elements. Idempotent."""

    @abstractmethod
    def create_entity(
        self,
        name: str,
        entity_type: str,
        embedding: list[float],
        project_id: int,
        attributes: dict[str, str] | None = None,
    ) -> str:
        """Create an entity node. Returns UUID."""

    @abstractmethod
    def find_similar_entities(
        self,
        embedding: list[float],
        entity_type: str,
        project_id: int,
        threshold: float = 0.85,
    ) -> list[Entity]:
        """Find entities with similar name embeddings. For entity resolution."""

    @abstractmethod
    def create_statement(
        self,
        fact: str,
        embedding: list[float],
        aspect: str,
        episode_id: int,
        project_id: int,
        valid_at: str | None = None,
        attributes: dict[str, str] | None = None,
    ) -> str:
        """Create a statement node. Returns UUID."""

    @abstractmethod
    def create_triple(
        self,
        statement_id: str,
        subject_id: str,
        predicate: str,
        object_id: str | None = None,
        object_value: str | None = None,
    ) -> None:
        """Link a statement to its subject entity (and optionally an object entity).

        If object_id is provided, creates: (subject)-[:SUBJECT]->(statement)<-[:OBJECT]-(object)
        If object_value is provided instead, stores the literal on the statement node.
        """

    @abstractmethod
    def find_contradictions(
        self,
        subject_id: str,
        predicate: str,
        project_id: int,
    ) -> list[Statement]:
        """Find existing valid statements with same subject+predicate (potential contradictions)."""

    @abstractmethod
    def invalidate_statement(
        self,
        statement_id: str,
        invalidated_by: str,
    ) -> None:
        """Mark a statement as invalid (superseded by a newer one)."""

    @abstractmethod
    def find_entity_statements(
        self,
        entity_id: str,
        aspects: list[str] | None = None,
    ) -> list[Statement]:
        """Get all valid statements involving an entity, optionally filtered by aspects."""

    @abstractmethod
    def find_entity_episodes(self, entity_id: str) -> list[int]:
        """Get PostgreSQL memory IDs (episode_ids) linked to an entity's statements."""

    @abstractmethod
    def bfs_traverse(
        self,
        start_entity_id: str,
        max_depth: int = 3,
    ) -> list[Statement]:
        """BFS from an entity, returning statements found along the path."""

    @abstractmethod
    def find_connecting_statements(
        self,
        entity_a_id: str,
        entity_b_id: str,
    ) -> list[Statement]:
        """Find statements on paths connecting two entities."""

    @abstractmethod
    def search_entities_by_embedding(
        self,
        embedding: list[float],
        project_id: int,
        limit: int = 10,
    ) -> list[Entity]:
        """Vector search over entity name embeddings."""

    @abstractmethod
    def search_statements_by_aspect(
        self,
        aspects: list[str],
        project_id: int,
    ) -> list[int]:
        """Find episode IDs of statements matching given aspects."""

    @abstractmethod
    def search_entities_fulltext(
        self,
        query: str,
        project_id: int,
        limit: int = 10,
    ) -> list[Entity]:
        """Fulltext search over entity names."""
