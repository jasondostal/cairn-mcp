"""Neo4j implementation of GraphProvider."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from cairn.graph.config import Neo4jConfig
from cairn.graph.interface import Entity, GraphProvider, Statement, ThinkingSequenceNode, ThoughtNode, TaskNode, WorkItemNode

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
            # ThinkingSequence constraints + indexes (v0.44.0)
            "CREATE CONSTRAINT thinking_seq_uuid IF NOT EXISTS FOR (ts:ThinkingSequence) REQUIRE ts.uuid IS UNIQUE",
            "CREATE INDEX thinking_seq_project IF NOT EXISTS FOR (ts:ThinkingSequence) ON (ts.project_id)",
            "CREATE INDEX thinking_seq_pg_id IF NOT EXISTS FOR (ts:ThinkingSequence) ON (ts.pg_id)",
            # Thought constraints + indexes (v0.44.0)
            "CREATE CONSTRAINT thought_uuid IF NOT EXISTS FOR (t:Thought) REQUIRE t.uuid IS UNIQUE",
            "CREATE INDEX thought_pg_id IF NOT EXISTS FOR (t:Thought) ON (t.pg_id)",
            # Task constraints + indexes (v0.44.0)
            "CREATE CONSTRAINT task_uuid IF NOT EXISTS FOR (tk:Task) REQUIRE tk.uuid IS UNIQUE",
            "CREATE INDEX task_project IF NOT EXISTS FOR (tk:Task) ON (tk.project_id)",
            "CREATE INDEX task_pg_id IF NOT EXISTS FOR (tk:Task) ON (tk.pg_id)",
            # WorkItem constraints + indexes (v0.47.0)
            "CREATE CONSTRAINT work_item_uuid IF NOT EXISTS FOR (wi:WorkItem) REQUIRE wi.uuid IS UNIQUE",
            "CREATE INDEX work_item_project IF NOT EXISTS FOR (wi:WorkItem) ON (wi.project_id)",
            "CREATE INDEX work_item_pg_id IF NOT EXISTS FOR (wi:WorkItem) ON (wi.pg_id)",
            "CREATE INDEX work_item_status IF NOT EXISTS FOR (wi:WorkItem) ON (wi.status)",
            "CREATE INDEX work_item_short_id IF NOT EXISTS FOR (wi:WorkItem) ON (wi.short_id)",
        ]

        # Vector indexes need separate handling — they use different syntax
        vector_statements = [
            """CREATE VECTOR INDEX entity_name_vec IF NOT EXISTS
               FOR (e:Entity) ON (e.name_embedding)
               OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}""",
            """CREATE VECTOR INDEX statement_fact_vec IF NOT EXISTS
               FOR (s:Statement) ON (s.fact_embedding)
               OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}""",
            # Thought content vector index (v0.44.0)
            """CREATE VECTOR INDEX thought_content_vec IF NOT EXISTS
               FOR (t:Thought) ON (t.content_embedding)
               OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}""",
            # WorkItem content vector index (v0.47.0)
            """CREATE VECTOR INDEX work_item_content_vec IF NOT EXISTS
               FOR (wi:WorkItem) ON (wi.content_embedding)
               OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}""",
        ]

        # Fulltext indexes
        fulltext_statements = [
            "CREATE FULLTEXT INDEX entity_name_ft IF NOT EXISTS FOR (e:Entity) ON EACH [e.name]",
            "CREATE FULLTEXT INDEX statement_fact_ft IF NOT EXISTS FOR (s:Statement) ON EACH [s.fact]",
            # WorkItem title fulltext (v0.47.0)
            "CREATE FULLTEXT INDEX work_item_title_ft IF NOT EXISTS FOR (wi:WorkItem) ON EACH [wi.title]",
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
        threshold: float = 0.0,
    ) -> list[Entity]:
        with self._session() as session:
            result = session.run(
                """
                CALL db.index.vector.queryNodes('entity_name_vec', $limit, $embedding)
                YIELD node, score
                WHERE node.project_id = $pid AND score > $threshold
                RETURN node.uuid AS uuid, node.name AS name, node.entity_type AS entity_type,
                       node.project_id AS project_id, node.attributes AS attributes, score
                ORDER BY score DESC
                """,
                embedding=embedding,
                pid=project_id,
                limit=limit,
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

    def get_known_entities(
        self,
        project_id: int,
        limit: int = 200,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity)
                WHERE e.project_id = $pid
                RETURN DISTINCT e.name AS name, e.entity_type AS entity_type
                ORDER BY e.name
                LIMIT $limit
                """,
                pid=project_id,
                limit=limit,
            )
            return [{"name": r["name"], "entity_type": r["entity_type"]} for r in result]

    def find_similar_entities_any_type(
        self,
        embedding: list[float],
        project_id: int,
        threshold: float = 0.95,
    ) -> list[Entity]:
        with self._session() as session:
            result = session.run(
                """
                CALL db.index.vector.queryNodes('entity_name_vec', 5, $embedding)
                YIELD node, score
                WHERE node.project_id = $pid AND score > $threshold
                RETURN node.uuid AS uuid, node.name AS name, node.entity_type AS entity_type,
                       node.project_id AS project_id, node.attributes AS attributes, score
                ORDER BY score DESC
                """,
                embedding=embedding,
                pid=project_id,
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

    def merge_entities(
        self,
        canonical_id: str,
        duplicate_id: str,
    ) -> dict:
        with self._session() as session:
            # Move SUBJECT relationships
            subj_result = session.run(
                """
                MATCH (dup:Entity {uuid: $dup_id})-[r:SUBJECT]->(s:Statement)
                MATCH (canon:Entity {uuid: $canon_id})
                MERGE (canon)-[:SUBJECT {predicate: r.predicate}]->(s)
                DELETE r
                RETURN count(r) AS moved
                """,
                dup_id=duplicate_id,
                canon_id=canonical_id,
            )
            subj_moved = subj_result.single()["moved"]

            # Move OBJECT relationships
            obj_result = session.run(
                """
                MATCH (dup:Entity {uuid: $dup_id})-[r:OBJECT]->(s:Statement)
                MATCH (canon:Entity {uuid: $canon_id})
                MERGE (canon)-[:OBJECT]->(s)
                DELETE r
                RETURN count(r) AS moved
                """,
                dup_id=duplicate_id,
                canon_id=canonical_id,
            )
            obj_moved = obj_result.single()["moved"]

            # Delete duplicate entity
            session.run(
                "MATCH (e:Entity {uuid: $dup_id}) DELETE e",
                dup_id=duplicate_id,
            )

            return {
                "subject_edges_moved": subj_moved,
                "object_edges_moved": obj_moved,
                "duplicate_deleted": duplicate_id,
            }

    # -- Temporal queries (v0.37.0) --

    def recent_activity(
        self,
        project_id: int | None,
        since: str,
        limit: int = 20,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (subj:Entity)-[:SUBJECT]->(s:Statement)
                WHERE ($pid IS NULL OR s.project_id = $pid)
                  AND s.created_at > $since AND s.invalid_at IS NULL
                  AND subj.entity_type IN ['Person', 'Organization', 'Project', 'Task', 'Event']
                OPTIONAL MATCH (obj:Entity)-[:OBJECT]->(s)
                RETURN s.uuid AS uuid, s.fact AS fact, s.aspect AS aspect,
                       s.episode_id AS episode_id, s.created_at AS created_at,
                       subj.name AS subject_name, subj.entity_type AS subject_type,
                       obj.name AS object_name, obj.entity_type AS object_type
                ORDER BY s.created_at DESC
                LIMIT $limit
                """,
                pid=project_id,
                since=since,
                limit=limit,
            )
            return [dict(r) for r in result]

    def session_context(
        self,
        episode_ids: list[int],
        project_id: int,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (subj:Entity)-[:SUBJECT]->(s:Statement)
                WHERE s.episode_id IN $episode_ids AND s.invalid_at IS NULL
                OPTIONAL MATCH (obj:Entity)-[:OBJECT]->(s)
                RETURN s.episode_id AS episode_id, s.fact AS fact, s.aspect AS aspect,
                       subj.name AS subject, obj.name AS object
                ORDER BY s.episode_id, s.created_at
                """,
                episode_ids=episode_ids,
            )
            return [dict(r) for r in result]

    def temporal_entities(
        self,
        project_id: int,
        since: str,
        until: str | None = None,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity)-[:SUBJECT|OBJECT]-(s:Statement)
                WHERE s.project_id = $pid AND s.created_at > $since
                  AND ($until IS NULL OR s.created_at < $until)
                  AND s.invalid_at IS NULL
                RETURN e.uuid AS uuid, e.name AS name, e.entity_type AS entity_type,
                       count(s) AS activity_count
                ORDER BY activity_count DESC
                """,
                pid=project_id,
                since=since,
                until=until,
            )
            return [dict(r) for r in result]

    # -- Object linking + graph search (v0.37.0) --

    def find_dangling_objects(
        self,
        project_id: int,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (s:Statement)
                WHERE s.project_id = $pid AND s.object_value IS NOT NULL
                  AND s.invalid_at IS NULL
                RETURN s.uuid AS uuid, s.object_value AS object_value
                """,
                pid=project_id,
            )
            return [dict(r) for r in result]

    def link_object_entity(
        self,
        statement_id: str,
        entity_id: str,
    ) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (obj:Entity {uuid: $entity_id})
                MATCH (stmt:Statement {uuid: $statement_id})
                MERGE (obj)-[:OBJECT]->(stmt)
                SET stmt.object_value = NULL
                """,
                entity_id=entity_id,
                statement_id=statement_id,
            )

    def graph_neighbor_episodes(
        self,
        candidate_episode_ids: list[int],
        project_id: int,
        limit: int = 50,
    ) -> dict[int, int]:
        if not candidate_episode_ids:
            return {}
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity)-[:SUBJECT|OBJECT]-(s1:Statement)
                WHERE s1.episode_id IN $candidate_ids AND s1.invalid_at IS NULL
                WITH collect(DISTINCT e) AS shared_entities,
                     collect(DISTINCT s1.episode_id) AS seeds
                UNWIND shared_entities AS e
                MATCH (e)-[:SUBJECT|OBJECT]-(s2:Statement)
                WHERE s2.invalid_at IS NULL
                  AND NOT s2.episode_id IN seeds
                  AND s2.project_id = $pid
                RETURN s2.episode_id AS memory_id, count(DISTINCT e) AS shared_entities
                ORDER BY shared_entities DESC
                LIMIT $limit
                """,
                candidate_ids=candidate_episode_ids,
                pid=project_id,
                limit=limit,
            )
            return {r["memory_id"]: r["shared_entities"] for r in result}

    # -- Thinking sequence + task graph nodes (v0.44.0) --

    def create_thinking_sequence(
        self,
        pg_id: int,
        project_id: int,
        goal: str,
        status: str = "active",
    ) -> str:
        seq_uuid = str(uuid.uuid4())
        with self._session() as session:
            session.run(
                """
                CREATE (ts:ThinkingSequence {
                    uuid: $uuid,
                    pg_id: $pg_id,
                    project_id: $project_id,
                    goal: $goal,
                    status: $status,
                    created_at: $now
                })
                """,
                uuid=seq_uuid,
                pg_id=pg_id,
                project_id=project_id,
                goal=goal,
                status=status,
                now=datetime.now(timezone.utc).isoformat(),
            )
        return seq_uuid

    def create_thought(
        self,
        pg_id: int,
        sequence_uuid: str,
        thought_type: str,
        content: str,
        content_embedding: list[float] | None = None,
    ) -> str:
        thought_uuid = str(uuid.uuid4())
        with self._session() as session:
            session.run(
                """
                CREATE (t:Thought {
                    uuid: $uuid,
                    pg_id: $pg_id,
                    thought_type: $thought_type,
                    content: $content,
                    content_embedding: $embedding,
                    created_at: $now
                })
                """,
                uuid=thought_uuid,
                pg_id=pg_id,
                thought_type=thought_type,
                content=content,
                embedding=content_embedding,
                now=datetime.now(timezone.utc).isoformat(),
            )
            # CONTAINS edge: sequence -> thought
            session.run(
                """
                MATCH (ts:ThinkingSequence {uuid: $seq_uuid})
                MATCH (t:Thought {uuid: $thought_uuid})
                MERGE (ts)-[:CONTAINS]->(t)
                """,
                seq_uuid=sequence_uuid,
                thought_uuid=thought_uuid,
            )
        return thought_uuid

    def complete_thinking_sequence(self, sequence_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (ts:ThinkingSequence {uuid: $uuid})
                SET ts.status = 'completed', ts.completed_at = $now
                """,
                uuid=sequence_uuid,
                now=datetime.now(timezone.utc).isoformat(),
            )

    def create_task(
        self,
        pg_id: int,
        project_id: int,
        description: str,
        status: str = "pending",
    ) -> str:
        task_uuid = str(uuid.uuid4())
        with self._session() as session:
            session.run(
                """
                CREATE (tk:Task {
                    uuid: $uuid,
                    pg_id: $pg_id,
                    project_id: $project_id,
                    description: $description,
                    status: $status,
                    created_at: $now
                })
                """,
                uuid=task_uuid,
                pg_id=pg_id,
                project_id=project_id,
                description=description,
                status=status,
                now=datetime.now(timezone.utc).isoformat(),
            )
        return task_uuid

    def complete_task(self, task_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (tk:Task {uuid: $uuid})
                SET tk.status = 'completed', tk.completed_at = $now
                """,
                uuid=task_uuid,
                now=datetime.now(timezone.utc).isoformat(),
            )

    def link_task_to_memory(self, task_uuid: str, episode_id: int) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (tk:Task {uuid: $task_uuid})
                MATCH (s:Statement {episode_id: $episode_id})
                WHERE s.invalid_at IS NULL
                MERGE (tk)-[:LINKED_TO]->(s)
                """,
                task_uuid=task_uuid,
                episode_id=episode_id,
            )

    def link_thought_to_entities(
        self,
        thought_uuid: str,
        entity_uuids: list[str],
    ) -> None:
        with self._session() as session:
            for entity_uuid in entity_uuids:
                session.run(
                    """
                    MATCH (t:Thought {uuid: $thought_uuid})
                    MATCH (e:Entity {uuid: $entity_uuid})
                    MERGE (t)-[:MENTIONS]->(e)
                    """,
                    thought_uuid=thought_uuid,
                    entity_uuid=entity_uuid,
                )

    def recent_thinking_activity(
        self,
        project_id: int | None,
        since: str,
        limit: int = 10,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (ts:ThinkingSequence)
                WHERE ($pid IS NULL OR ts.project_id = $pid)
                  AND ts.created_at > $since
                OPTIONAL MATCH (ts)-[:CONTAINS]->(t:Thought)
                RETURN ts.uuid AS uuid, ts.pg_id AS pg_id, ts.goal AS goal,
                       ts.status AS status, ts.created_at AS created_at,
                       ts.project_id AS project_id,
                       count(t) AS thought_count
                ORDER BY ts.created_at DESC
                LIMIT $limit
                """,
                pid=project_id,
                since=since,
                limit=limit,
            )
            return [dict(r) for r in result]

    # -- Work item graph nodes (v0.47.0) --

    def add_work_item_parent_edge(self, child_uuid: str, parent_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (parent:WorkItem {uuid: $parent_uuid})
                MATCH (child:WorkItem {uuid: $child_uuid})
                MERGE (parent)-[:PARENT_OF]->(child)
                """,
                parent_uuid=parent_uuid,
                child_uuid=child_uuid,
            )

    def add_work_item_blocks_edge(self, blocker_uuid: str, blocked_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (blocker:WorkItem {uuid: $blocker_uuid})
                MATCH (blocked:WorkItem {uuid: $blocked_uuid})
                MERGE (blocker)-[:BLOCKS]->(blocked)
                """,
                blocker_uuid=blocker_uuid,
                blocked_uuid=blocked_uuid,
            )

    def remove_work_item_blocks_edge(self, blocker_uuid: str, blocked_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (blocker:WorkItem {uuid: $blocker_uuid})-[r:BLOCKS]->(blocked:WorkItem {uuid: $blocked_uuid})
                DELETE r
                """,
                blocker_uuid=blocker_uuid,
                blocked_uuid=blocked_uuid,
            )

    def update_work_item_risk_tier(self, work_item_uuid: str, risk_tier: int) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (wi:WorkItem {uuid: $uuid})
                SET wi.risk_tier = $risk_tier, wi.updated_at = $now
                """,
                uuid=work_item_uuid,
                risk_tier=risk_tier,
                now=datetime.now(timezone.utc).isoformat(),
            )

    def link_work_item_to_memory(self, work_item_uuid: str, episode_id: int) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (wi:WorkItem {uuid: $wi_uuid})
                MATCH (s:Statement {episode_id: $episode_id})
                WHERE s.invalid_at IS NULL
                MERGE (wi)-[:LINKED_TO]->(s)
                """,
                wi_uuid=work_item_uuid,
                episode_id=episode_id,
            )

    def link_work_item_to_entity(self, work_item_uuid: str, entity_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (wi:WorkItem {uuid: $wi_uuid})
                MATCH (e:Entity {uuid: $entity_uuid})
                MERGE (wi)-[:MENTIONS]->(e)
                """,
                wi_uuid=work_item_uuid,
                entity_uuid=entity_uuid,
            )

    def work_item_ready_queue(self, project_id: int, limit: int = 10) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (wi:WorkItem {project_id: $pid})
                WHERE wi.status IN ['open', 'ready']
                  AND wi.assignee IS NULL
                  AND NOT EXISTS {
                    (blocker:WorkItem)-[:BLOCKS]->(wi)
                    WHERE NOT blocker.status IN ['done', 'cancelled']
                  }
                RETURN wi.pg_id AS id, wi.title AS title, wi.priority AS priority,
                       wi.short_id AS short_id, wi.item_type AS item_type
                ORDER BY wi.priority DESC, wi.created_at ASC
                LIMIT $limit
                """,
                pid=project_id,
                limit=limit,
            )
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # Idempotent ensure methods — used by event-driven graph projection
    # ------------------------------------------------------------------

    def ensure_work_item(self, pg_id: int, project_id: int, **fields) -> str:
        """MERGE WorkItem by pg_id. Creates if missing, updates if exists."""
        now = datetime.now(timezone.utc).isoformat()
        props = {k: v for k, v in fields.items() if v is not None}
        props["updated_at"] = now
        with self._session() as session:
            result = session.run(
                """
                MERGE (wi:WorkItem {pg_id: $pg_id})
                ON CREATE SET wi.uuid = $uuid, wi.project_id = $pid,
                              wi.created_at = $now, wi += $props
                ON MATCH SET  wi += $props
                RETURN wi.uuid AS uuid
                """,
                pg_id=pg_id,
                uuid=str(uuid.uuid4()),
                pid=project_id,
                now=now,
                props=props,
            )
            return result.single()["uuid"]

    def ensure_task(self, pg_id: int, project_id: int, **fields) -> str:
        """MERGE Task by pg_id. Creates if missing, updates if exists."""
        now = datetime.now(timezone.utc).isoformat()
        props = {k: v for k, v in fields.items() if v is not None}
        props["updated_at"] = now
        with self._session() as session:
            result = session.run(
                """
                MERGE (tk:Task {pg_id: $pg_id})
                ON CREATE SET tk.uuid = $uuid, tk.project_id = $pid,
                              tk.created_at = $now, tk += $props
                ON MATCH SET  tk += $props
                RETURN tk.uuid AS uuid
                """,
                pg_id=pg_id,
                uuid=str(uuid.uuid4()),
                pid=project_id,
                now=now,
                props=props,
            )
            return result.single()["uuid"]

    def ensure_thinking_sequence(self, pg_id: int, project_id: int, **fields) -> str:
        """MERGE ThinkingSequence by pg_id."""
        now = datetime.now(timezone.utc).isoformat()
        props = {k: v for k, v in fields.items() if v is not None}
        props["updated_at"] = now
        with self._session() as session:
            result = session.run(
                """
                MERGE (ts:ThinkingSequence {pg_id: $pg_id})
                ON CREATE SET ts.uuid = $uuid, ts.project_id = $pid,
                              ts.created_at = $now, ts += $props
                ON MATCH SET  ts += $props
                RETURN ts.uuid AS uuid
                """,
                pg_id=pg_id,
                uuid=str(uuid.uuid4()),
                pid=project_id,
                now=now,
                props=props,
            )
            return result.single()["uuid"]

    def ensure_thought(self, pg_id: int, sequence_pg_id: int, **fields) -> str:
        """MERGE Thought by pg_id and link to parent sequence."""
        now = datetime.now(timezone.utc).isoformat()
        props = {k: v for k, v in fields.items() if v is not None}
        props["updated_at"] = now
        with self._session() as session:
            result = session.run(
                """
                MERGE (t:Thought {pg_id: $pg_id})
                ON CREATE SET t.uuid = $uuid, t.created_at = $now, t += $props
                ON MATCH SET  t += $props
                WITH t
                OPTIONAL MATCH (ts:ThinkingSequence {pg_id: $seq_pg_id})
                WHERE ts IS NOT NULL
                MERGE (ts)-[:CONTAINS]->(t)
                RETURN t.uuid AS uuid
                """,
                pg_id=pg_id,
                uuid=str(uuid.uuid4()),
                seq_pg_id=sequence_pg_id,
                now=now,
                props=props,
            )
            return result.single()["uuid"]

    def get_knowledge_graph_visualization(
        self,
        project_id: int | None = None,
        entity_types: list[str] | None = None,
        limit: int = 500,
    ) -> dict:
        """Return entities and their relationships for force-directed graph visualization.

        Returns nodes (entities) and edges (statement triples: subject -[predicate]-> object).
        """
        with self._session() as session:
            # Build WHERE clause
            entity_where = ["s.invalid_at IS NULL"]
            params: dict = {"limit": limit}
            if project_id is not None:
                entity_where.append("e.project_id = $pid")
                params["pid"] = project_id
            if entity_types:
                entity_where.append("e.entity_type IN $etypes")
                params["etypes"] = entity_types

            where_clause = " AND ".join(entity_where)

            # Fetch entities that have at least one valid statement
            entity_result = session.run(
                f"""
                MATCH (e:Entity)-[:SUBJECT|OBJECT]-(s:Statement)
                WHERE {where_clause}
                WITH e, count(DISTINCT s) AS stmt_count
                RETURN e.uuid AS uuid, e.name AS name, e.entity_type AS entity_type,
                       e.project_id AS project_id, stmt_count
                ORDER BY stmt_count DESC
                LIMIT $limit
                """,
                **params,
            )
            entities = [dict(r) for r in entity_result]
            entity_uuids = {e["uuid"] for e in entities}

            if not entity_uuids:
                return {"nodes": [], "edges": [], "stats": {
                    "node_count": 0, "edge_count": 0, "entity_types": {},
                }}

            # Fetch edges: triples where both subject and object are in our entity set
            edge_result = session.run(
                """
                MATCH (subj:Entity)-[r:SUBJECT]->(s:Statement)<-[:OBJECT]-(obj:Entity)
                WHERE subj.uuid IN $uuids AND obj.uuid IN $uuids
                  AND s.invalid_at IS NULL
                RETURN subj.uuid AS source, obj.uuid AS target,
                       r.predicate AS predicate, s.fact AS fact,
                       s.aspect AS aspect, s.episode_id AS episode_id
                """,
                uuids=list(entity_uuids),
            )
            edges = [dict(r) for r in edge_result]

            # Stats
            type_counts: dict[str, int] = {}
            for e in entities:
                t = e["entity_type"]
                type_counts[t] = type_counts.get(t, 0) + 1

            return {
                "nodes": entities,
                "edges": edges,
                "stats": {
                    "node_count": len(entities),
                    "edge_count": len(edges),
                    "entity_types": type_counts,
                },
            }
