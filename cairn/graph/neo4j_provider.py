"""Neo4j implementation of GraphProvider."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from cairn.graph.config import Neo4jConfig
from cairn.graph.interface import Entity, GraphProvider, Statement

logger = logging.getLogger(__name__)


class Neo4jGraphProvider(GraphProvider):
    """Knowledge graph backed by Neo4j 5 Community Edition."""

    def __init__(self, config: Neo4jConfig):
        self.config = config
        self._driver = None

    def connect(self) -> None:
        """Open connection to Neo4j."""
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(
            self.config.uri,
            auth=(self.config.user, self.config.password),
        )
        # Verify connectivity
        self._driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", self.config.uri)

    def close(self) -> None:
        """Close Neo4j driver."""
        if self._driver:
            self._driver.close()
            self._driver = None

    @property
    def _db(self) -> str:
        return self.config.database

    def _session(self):
        """Create a Neo4j session."""
        return self._driver.session(database=self._db)

    def ensure_schema(self) -> None:
        """Create constraints and indexes. Idempotent — safe to call on every startup."""
        statements = [
            # Entity constraints + indexes
            "CREATE CONSTRAINT entity_uuid IF NOT EXISTS FOR (e:Entity) REQUIRE e.uuid IS UNIQUE",
            "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
            "CREATE INDEX entity_project IF NOT EXISTS FOR (e:Entity) ON (e.project_id)",
            # Statement constraints + indexes
            "CREATE CONSTRAINT statement_uuid IF NOT EXISTS FOR (s:Statement) REQUIRE s.uuid IS UNIQUE",
            "CREATE INDEX statement_aspect IF NOT EXISTS FOR (s:Statement) ON (s.aspect)",
            "CREATE INDEX statement_project IF NOT EXISTS FOR (s:Statement) ON (s.project_id)",
            "CREATE INDEX statement_episode IF NOT EXISTS FOR (s:Statement) ON (s.episode_id)",
        ]

        # Vector indexes need separate handling — they use different syntax
        vector_statements = [
            """CREATE VECTOR INDEX entity_name_vec IF NOT EXISTS
               FOR (e:Entity) ON (e.name_embedding)
               OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}""",
            """CREATE VECTOR INDEX statement_fact_vec IF NOT EXISTS
               FOR (s:Statement) ON (s.fact_embedding)
               OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}""",
        ]

        # Fulltext indexes
        fulltext_statements = [
            "CREATE FULLTEXT INDEX entity_name_ft IF NOT EXISTS FOR (e:Entity) ON EACH [e.name]",
            "CREATE FULLTEXT INDEX statement_fact_ft IF NOT EXISTS FOR (s:Statement) ON EACH [s.fact]",
        ]

        with self._session() as session:
            for stmt in statements + vector_statements + fulltext_statements:
                try:
                    session.run(stmt)
                except Exception as e:
                    # Log but don't fail — index might already exist in different form
                    logger.debug("Schema statement skipped: %s — %s", stmt[:60], e)

        logger.info("Neo4j schema ensured")

    def create_entity(
        self,
        name: str,
        entity_type: str,
        embedding: list[float],
        project_id: int,
        attributes: dict[str, str] | None = None,
    ) -> str:
        entity_uuid = str(uuid.uuid4())
        attrs_json = json.dumps(attributes or {})

        with self._session() as session:
            session.run(
                """
                CREATE (e:Entity {
                    uuid: $uuid,
                    name: $name,
                    entity_type: $entity_type,
                    name_embedding: $embedding,
                    project_id: $project_id,
                    attributes: $attributes,
                    created_at: $now
                })
                """,
                uuid=entity_uuid,
                name=name,
                entity_type=entity_type,
                embedding=embedding,
                project_id=project_id,
                attributes=attrs_json,
                now=datetime.now(timezone.utc).isoformat(),
            )
        return entity_uuid

    def find_similar_entities(
        self,
        embedding: list[float],
        entity_type: str,
        project_id: int,
        threshold: float = 0.85,
    ) -> list[Entity]:
        with self._session() as session:
            result = session.run(
                """
                CALL db.index.vector.queryNodes('entity_name_vec', 5, $embedding)
                YIELD node, score
                WHERE node.project_id = $pid AND node.entity_type = $type AND score > $threshold
                RETURN node.uuid AS uuid, node.name AS name, node.entity_type AS entity_type,
                       node.project_id AS project_id, node.attributes AS attributes, score
                ORDER BY score DESC
                """,
                embedding=embedding,
                pid=project_id,
                type=entity_type,
                threshold=threshold,
            )
            return [
                Entity(
                    uuid=r["uuid"],
                    name=r["name"],
                    entity_type=r["entity_type"],
                    project_id=r["project_id"],
                    attributes=json.loads(r["attributes"]) if r["attributes"] else {},
                )
                for r in result
            ]

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
        stmt_uuid = str(uuid.uuid4())
        attrs_json = json.dumps(attributes or {})

        with self._session() as session:
            session.run(
                """
                CREATE (s:Statement {
                    uuid: $uuid,
                    fact: $fact,
                    fact_embedding: $embedding,
                    aspect: $aspect,
                    episode_id: $episode_id,
                    project_id: $project_id,
                    valid_at: $valid_at,
                    attributes: $attributes,
                    created_at: $now
                })
                """,
                uuid=stmt_uuid,
                fact=fact,
                embedding=embedding,
                aspect=aspect,
                episode_id=episode_id,
                project_id=project_id,
                valid_at=valid_at,
                attributes=attrs_json,
                now=datetime.now(timezone.utc).isoformat(),
            )
        return stmt_uuid

    def create_triple(
        self,
        statement_id: str,
        subject_id: str,
        predicate: str,
        object_id: str | None = None,
        object_value: str | None = None,
    ) -> None:
        with self._session() as session:
            # Subject -> Statement
            session.run(
                """
                MATCH (subj:Entity {uuid: $subject_id})
                MATCH (stmt:Statement {uuid: $statement_id})
                MERGE (subj)-[:SUBJECT {predicate: $predicate}]->(stmt)
                """,
                subject_id=subject_id,
                statement_id=statement_id,
                predicate=predicate,
            )

            # Object entity -> Statement (if entity reference)
            if object_id:
                session.run(
                    """
                    MATCH (obj:Entity {uuid: $object_id})
                    MATCH (stmt:Statement {uuid: $statement_id})
                    MERGE (obj)-[:OBJECT]->(stmt)
                    """,
                    object_id=object_id,
                    statement_id=statement_id,
                )
            elif object_value:
                # Store literal value on statement
                session.run(
                    """
                    MATCH (stmt:Statement {uuid: $statement_id})
                    SET stmt.object_value = $object_value
                    """,
                    statement_id=statement_id,
                    object_value=object_value,
                )

    def find_contradictions(
        self,
        subject_id: str,
        predicate: str,
        project_id: int,
    ) -> list[Statement]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (subj:Entity {uuid: $subject_id})-[r:SUBJECT {predicate: $predicate}]->(s:Statement)
                WHERE s.project_id = $pid AND s.invalid_at IS NULL
                RETURN s.uuid AS uuid, s.fact AS fact, s.aspect AS aspect,
                       s.episode_id AS episode_id, s.project_id AS project_id,
                       s.valid_at AS valid_at
                """,
                subject_id=subject_id,
                predicate=predicate,
                pid=project_id,
            )
            return [
                Statement(
                    uuid=r["uuid"],
                    fact=r["fact"],
                    aspect=r["aspect"],
                    episode_id=r["episode_id"],
                    project_id=r["project_id"],
                    valid_at=r["valid_at"],
                )
                for r in result
            ]

    def invalidate_statement(
        self,
        statement_id: str,
        invalidated_by: str,
    ) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (s:Statement {uuid: $statement_id})
                SET s.invalid_at = $now, s.invalidated_by = $invalidated_by
                """,
                statement_id=statement_id,
                now=datetime.now(timezone.utc).isoformat(),
                invalidated_by=invalidated_by,
            )

    def find_entity_statements(
        self,
        entity_id: str,
        aspects: list[str] | None = None,
    ) -> list[Statement]:
        if aspects:
            query = """
                MATCH (e:Entity {uuid: $entity_id})-[:SUBJECT|OBJECT]-(s:Statement)
                WHERE s.invalid_at IS NULL AND s.aspect IN $aspects
                RETURN DISTINCT s.uuid AS uuid, s.fact AS fact, s.aspect AS aspect,
                       s.episode_id AS episode_id, s.project_id AS project_id,
                       s.valid_at AS valid_at
            """
            params = {"entity_id": entity_id, "aspects": aspects}
        else:
            query = """
                MATCH (e:Entity {uuid: $entity_id})-[:SUBJECT|OBJECT]-(s:Statement)
                WHERE s.invalid_at IS NULL
                RETURN DISTINCT s.uuid AS uuid, s.fact AS fact, s.aspect AS aspect,
                       s.episode_id AS episode_id, s.project_id AS project_id,
                       s.valid_at AS valid_at
            """
            params = {"entity_id": entity_id}

        with self._session() as session:
            result = session.run(query, **params)
            return [
                Statement(
                    uuid=r["uuid"],
                    fact=r["fact"],
                    aspect=r["aspect"],
                    episode_id=r["episode_id"],
                    project_id=r["project_id"],
                    valid_at=r["valid_at"],
                )
                for r in result
            ]

    def find_entity_episodes(self, entity_id: str) -> list[int]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity {uuid: $entity_id})-[:SUBJECT|OBJECT]-(s:Statement)
                WHERE s.invalid_at IS NULL
                RETURN DISTINCT s.episode_id AS episode_id
                """,
                entity_id=entity_id,
            )
            return [r["episode_id"] for r in result if r["episode_id"] is not None]

    def bfs_traverse(
        self,
        start_entity_id: str,
        max_depth: int = 3,
    ) -> list[Statement]:
        with self._session() as session:
            result = session.run(
                """
                MATCH path = (start:Entity {uuid: $id})-[*1..{depth}]-(end)
                UNWIND nodes(path) AS n
                WITH n WHERE n:Statement AND n.invalid_at IS NULL
                RETURN DISTINCT n.uuid AS uuid, n.fact AS fact, n.aspect AS aspect,
                       n.episode_id AS episode_id, n.project_id AS project_id,
                       n.valid_at AS valid_at
                """.replace("{depth}", str(max_depth)),
                id=start_entity_id,
            )
            return [
                Statement(
                    uuid=r["uuid"],
                    fact=r["fact"],
                    aspect=r["aspect"],
                    episode_id=r["episode_id"],
                    project_id=r["project_id"],
                    valid_at=r["valid_at"],
                )
                for r in result
            ]

    def find_connecting_statements(
        self,
        entity_a_id: str,
        entity_b_id: str,
    ) -> list[Statement]:
        with self._session() as session:
            result = session.run(
                """
                MATCH path = (a:Entity {uuid: $entity_a})-[*1..3]-(b:Entity {uuid: $entity_b})
                UNWIND nodes(path) AS n
                WITH n WHERE n:Statement AND n.invalid_at IS NULL
                RETURN DISTINCT n.uuid AS uuid, n.fact AS fact, n.aspect AS aspect,
                       n.episode_id AS episode_id, n.project_id AS project_id,
                       n.valid_at AS valid_at
                """,
                entity_a=entity_a_id,
                entity_b=entity_b_id,
            )
            return [
                Statement(
                    uuid=r["uuid"],
                    fact=r["fact"],
                    aspect=r["aspect"],
                    episode_id=r["episode_id"],
                    project_id=r["project_id"],
                    valid_at=r["valid_at"],
                )
                for r in result
            ]

    def search_entities_by_embedding(
        self,
        embedding: list[float],
        project_id: int,
        limit: int = 10,
    ) -> list[Entity]:
        with self._session() as session:
            result = session.run(
                """
                CALL db.index.vector.queryNodes('entity_name_vec', $limit, $embedding)
                YIELD node, score
                WHERE node.project_id = $pid
                RETURN node.uuid AS uuid, node.name AS name, node.entity_type AS entity_type,
                       node.project_id AS project_id, node.attributes AS attributes, score
                ORDER BY score DESC
                """,
                embedding=embedding,
                pid=project_id,
                limit=limit,
            )
            return [
                Entity(
                    uuid=r["uuid"],
                    name=r["name"],
                    entity_type=r["entity_type"],
                    project_id=r["project_id"],
                    attributes=json.loads(r["attributes"]) if r["attributes"] else {},
                )
                for r in result
            ]

    def search_statements_by_aspect(
        self,
        aspects: list[str],
        project_id: int,
    ) -> list[int]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (s:Statement)
                WHERE s.aspect IN $aspects AND s.invalid_at IS NULL AND s.project_id = $pid
                RETURN DISTINCT s.episode_id AS episode_id
                """,
                aspects=aspects,
                pid=project_id,
            )
            return [r["episode_id"] for r in result if r["episode_id"] is not None]

    def search_entities_fulltext(
        self,
        query: str,
        project_id: int,
        limit: int = 10,
    ) -> list[Entity]:
        with self._session() as session:
            result = session.run(
                """
                CALL db.index.fulltext.queryNodes('entity_name_ft', $search_term)
                YIELD node, score
                WHERE node.project_id = $pid
                RETURN node.uuid AS uuid, node.name AS name, node.entity_type AS entity_type,
                       node.project_id AS project_id, node.attributes AS attributes
                ORDER BY score DESC
                LIMIT $limit
                """,
                search_term=query,
                pid=project_id,
                limit=limit,
            )
            return [
                Entity(
                    uuid=r["uuid"],
                    name=r["name"],
                    entity_type=r["entity_type"],
                    project_id=r["project_id"],
                    attributes=json.loads(r["attributes"]) if r["attributes"] else {},
                )
                for r in result
            ]
