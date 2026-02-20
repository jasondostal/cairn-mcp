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


@dataclass
class ThinkingSequenceNode:
    """A thinking sequence node in the knowledge graph."""
    uuid: str
    pg_id: int
    project_id: int
    goal: str
    status: str


@dataclass
class ThoughtNode:
    """A thought node in the knowledge graph."""
    uuid: str
    pg_id: int
    sequence_uuid: str
    thought_type: str
    content: str


@dataclass
class TaskNode:
    """A task node in the knowledge graph."""
    uuid: str
    pg_id: int
    project_id: int
    description: str
    status: str


@dataclass
class WorkItemNode:
    """A work item node in the knowledge graph."""
    uuid: str
    pg_id: int
    project_id: int
    title: str
    description: str | None
    item_type: str
    priority: int
    status: str
    short_id: str
    risk_tier: int = 0
    gate_type: str | None = None


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
        threshold: float = 0.0,
    ) -> list[Entity]:
        """Vector search over entity name embeddings. Threshold filters by cosine similarity."""

    @abstractmethod
    def search_statements_by_aspect(
        self,
        aspects: list[str],
        project_id: int,
    ) -> list[int]:
        """Find episode IDs of statements matching given aspects."""

    @abstractmethod
    def get_known_entities(
        self,
        project_id: int,
        limit: int = 200,
    ) -> list[dict]:
        """Return existing entity names and types for canonicalization."""

    @abstractmethod
    def find_similar_entities_any_type(
        self,
        embedding: list[float],
        project_id: int,
        threshold: float = 0.95,
    ) -> list[Entity]:
        """Find entities with similar name embeddings, ignoring entity_type.

        Used as fallback for type-agnostic entity resolution (e.g. merging
        'Motes (Project)' and 'Motes (Concept)' into a single entity).
        Higher threshold than type-scoped matching to avoid false merges.
        """

    @abstractmethod
    def merge_entities(
        self,
        canonical_id: str,
        duplicate_id: str,
    ) -> dict:
        """Merge duplicate entity into canonical. Moves all relationships.

        Returns dict with counts of moved relationships.
        """

    @abstractmethod
    def recent_activity(
        self,
        project_id: int | None,
        since: str,
        limit: int = 20,
    ) -> list[dict]:
        """Recent statements with their subject/object entities. Boot orientation."""

    @abstractmethod
    def session_context(
        self,
        episode_ids: list[int],
        project_id: int,
    ) -> list[dict]:
        """Given memory IDs (episodes), return their entities and statements."""

    @abstractmethod
    def temporal_entities(
        self,
        project_id: int,
        since: str,
        until: str | None = None,
    ) -> list[dict]:
        """Entities active (had statements created) in a time window."""

    @abstractmethod
    def find_dangling_objects(
        self,
        project_id: int,
    ) -> list[dict]:
        """Find statements with string object_value (unlinked to entities)."""

    @abstractmethod
    def link_object_entity(
        self,
        statement_id: str,
        entity_id: str,
    ) -> None:
        """Create OBJECT edge and clear object_value on a statement."""

    @abstractmethod
    def graph_neighbor_episodes(
        self,
        candidate_episode_ids: list[int],
        project_id: int,
        limit: int = 50,
    ) -> dict[int, int]:
        """Find memories sharing entities with candidates.

        Returns {episode_id: shared_entity_count} for episodes NOT in candidates.
        """

    # -- Thinking sequence + task graph nodes (v0.44.0) --

    @abstractmethod
    def create_thinking_sequence(
        self,
        pg_id: int,
        project_id: int,
        goal: str,
        status: str = "active",
    ) -> str:
        """Create a ThinkingSequence node. Returns UUID."""

    @abstractmethod
    def create_thought(
        self,
        pg_id: int,
        sequence_uuid: str,
        thought_type: str,
        content: str,
        content_embedding: list[float] | None = None,
    ) -> str:
        """Create a Thought node linked to its sequence via CONTAINS. Returns UUID."""

    @abstractmethod
    def complete_thinking_sequence(self, sequence_uuid: str) -> None:
        """Mark a ThinkingSequence node as completed."""

    @abstractmethod
    def create_task(
        self,
        pg_id: int,
        project_id: int,
        description: str,
        status: str = "pending",
    ) -> str:
        """Create a Task node. Returns UUID."""

    @abstractmethod
    def complete_task(self, task_uuid: str) -> None:
        """Mark a Task node as completed."""

    @abstractmethod
    def link_task_to_memory(self, task_uuid: str, episode_id: int) -> None:
        """Create LINKED_TO edge between Task and Statement(s) for a memory."""

    @abstractmethod
    def link_thought_to_entities(
        self,
        thought_uuid: str,
        entity_uuids: list[str],
    ) -> None:
        """Create MENTIONS edges from Thought to Entity nodes."""

    @abstractmethod
    def recent_thinking_activity(
        self,
        project_id: int | None,
        since: str,
        limit: int = 10,
    ) -> list[dict]:
        """Recent thinking sequences with their goals and thought counts."""

    # -- Work item graph nodes (v0.47.0) --

    @abstractmethod
    def add_work_item_parent_edge(self, child_uuid: str, parent_uuid: str) -> None:
        """Create PARENT_OF edge: (parent)-[:PARENT_OF]->(child)."""

    @abstractmethod
    def add_work_item_blocks_edge(self, blocker_uuid: str, blocked_uuid: str) -> None:
        """Create BLOCKS edge: (blocker)-[:BLOCKS]->(blocked)."""

    @abstractmethod
    def remove_work_item_blocks_edge(self, blocker_uuid: str, blocked_uuid: str) -> None:
        """Remove BLOCKS edge between two work items."""

    @abstractmethod
    def update_work_item_risk_tier(self, work_item_uuid: str, risk_tier: int) -> None:
        """Update risk_tier on a WorkItem node."""

    @abstractmethod
    def link_work_item_to_memory(self, work_item_uuid: str, episode_id: int) -> None:
        """Create LINKED_TO edge between WorkItem and Statement(s) for a memory."""

    @abstractmethod
    def link_work_item_to_entity(self, work_item_uuid: str, entity_uuid: str) -> None:
        """Create MENTIONS edge between WorkItem and Entity."""

    @abstractmethod
    def work_item_ready_queue(self, project_id: int, limit: int = 10) -> list[dict]:
        """Return unblocked, unassigned work items ordered by priority."""

    # -- Idempotent ensure methods (event-driven projection) --

    @abstractmethod
    def ensure_work_item(self, pg_id: int, project_id: int, **fields) -> str:
        """MERGE a WorkItem node by pg_id. Creates if missing, updates if exists.
        Returns the node's uuid."""

    @abstractmethod
    def ensure_task(self, pg_id: int, project_id: int, **fields) -> str:
        """MERGE a Task node by pg_id. Returns uuid."""

    @abstractmethod
    def ensure_thinking_sequence(self, pg_id: int, project_id: int, **fields) -> str:
        """MERGE a ThinkingSequence node by pg_id. Returns uuid."""

    @abstractmethod
    def ensure_thought(self, pg_id: int, sequence_pg_id: int, **fields) -> str:
        """MERGE a Thought node by pg_id, link to parent sequence. Returns uuid."""
