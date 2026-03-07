"""Neo4j implementation of GraphProvider."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

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

        self._driver = GraphDatabase.driver(  # type: ignore[assignment]
            self.config.uri,
            auth=(self.config.user, self.config.password),
        )
        # Verify connectivity
        self._driver.verify_connectivity()  # type: ignore[attr-defined]
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
            # CodeFile constraints + indexes (v0.58.0)
            "CREATE CONSTRAINT code_file_uuid IF NOT EXISTS FOR (cf:CodeFile) REQUIRE cf.uuid IS UNIQUE",
            "CREATE INDEX code_file_project IF NOT EXISTS FOR (cf:CodeFile) ON (cf.project_id)",
            "CREATE INDEX code_file_path IF NOT EXISTS FOR (cf:CodeFile) ON (cf.path)",
            # CodeSymbol constraints + indexes (v0.58.0)
            "CREATE CONSTRAINT code_symbol_uuid IF NOT EXISTS FOR (cs:CodeSymbol) REQUIRE cs.uuid IS UNIQUE",
            "CREATE INDEX code_symbol_project IF NOT EXISTS FOR (cs:CodeSymbol) ON (cs.project_id)",
            "CREATE INDEX code_symbol_kind IF NOT EXISTS FOR (cs:CodeSymbol) ON (cs.kind)",
            "CREATE INDEX code_symbol_file IF NOT EXISTS FOR (cs:CodeSymbol) ON (cs.file_path)",
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
            # CodeSymbol fulltext (v0.58.0, expanded v0.71.0)
            "CREATE FULLTEXT INDEX code_symbol_name_ft IF NOT EXISTS FOR (cs:CodeSymbol) ON EACH [cs.name, cs.qualified_name, cs.signature, cs.docstring]",
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
                now=datetime.now(UTC).isoformat(),
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
                now=datetime.now(UTC).isoformat(),
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
                now=datetime.now(UTC).isoformat(),
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

    def update_entity(
        self,
        entity_id: str,
        name: str | None = None,
        entity_type: str | None = None,
        embedding: list[float] | None = None,
    ) -> bool:
        with self._session() as session:
            sets = []
            params: dict = {"uuid": entity_id}
            if name is not None:
                sets.append("e.name = $name")
                params["name"] = name
            if entity_type is not None:
                sets.append("e.entity_type = $entity_type")
                params["entity_type"] = entity_type
            if embedding is not None:
                sets.append("e.name_embedding = $embedding")
                params["embedding"] = embedding
            if not sets:
                return True
            result = session.run(
                f"MATCH (e:Entity {{uuid: $uuid}}) SET {', '.join(sets)} RETURN e.uuid AS uuid",
                **params,
            )
            return result.single() is not None

    def delete_entity(self, entity_id: str) -> dict:
        with self._session() as session:
            # Find statements where this entity is the ONLY subject/object
            # and delete those orphaned statements
            orphan_result = session.run(
                """
                MATCH (e:Entity {uuid: $uuid})-[:SUBJECT|OBJECT]->(s:Statement)
                WITH s
                WHERE size([(n)-[:SUBJECT|OBJECT]->(s) | n]) <= 1
                DETACH DELETE s
                RETURN count(s) AS deleted
                """,
                uuid=entity_id,
            )
            stmts_deleted = orphan_result.single()["deleted"]

            # Detach delete the entity itself (removes remaining edges)
            entity_result = session.run(
                "MATCH (e:Entity {uuid: $uuid}) DETACH DELETE e RETURN count(e) AS deleted",
                uuid=entity_id,
            )
            entity_deleted = entity_result.single()["deleted"]

            return {
                "entity_deleted": entity_deleted > 0,
                "orphaned_statements_deleted": stmts_deleted,
            }

    def get_entity(self, entity_id: str) -> Entity | None:
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity {uuid: $uuid})
                RETURN e.uuid AS uuid, e.name AS name, e.entity_type AS entity_type,
                       e.project_id AS project_id, e.attributes AS attributes
                """,
                uuid=entity_id,
            )
            record = result.single()
            if not record:
                return None
            return Entity(
                uuid=record["uuid"],
                name=record["name"],
                entity_type=record["entity_type"],
                project_id=record["project_id"],
                attributes=json.loads(record["attributes"]) if record["attributes"] else {},
            )

    def list_entities(
        self,
        project_id: int,
        search: str | None = None,
        entity_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        with self._session() as session:
            where = ["e.project_id = $pid"]
            params: dict = {"pid": project_id, "limit": limit}
            if entity_type:
                where.append("e.entity_type = $etype")
                params["etype"] = entity_type
            if search:
                where.append("toLower(e.name) CONTAINS toLower($search)")
                params["search"] = search

            result = session.run(
                f"""
                MATCH (e:Entity)
                WHERE {' AND '.join(where)}
                OPTIONAL MATCH (e)-[:SUBJECT|OBJECT]-(s:Statement)
                WHERE s.invalid_at IS NULL
                WITH e, count(DISTINCT s) AS stmt_count
                RETURN e.uuid AS uuid, e.name AS name, e.entity_type AS entity_type,
                       e.project_id AS project_id, stmt_count
                ORDER BY stmt_count DESC
                LIMIT $limit
                """,
                **params,
            )
            return [dict(r) for r in result]

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
                now=datetime.now(UTC).isoformat(),
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
                now=datetime.now(UTC).isoformat(),
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
                now=datetime.now(UTC).isoformat(),
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
                now=datetime.now(UTC).isoformat(),
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
                now=datetime.now(UTC).isoformat(),
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
                now=datetime.now(UTC).isoformat(),
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
        now = datetime.now(UTC).isoformat()
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
        now = datetime.now(UTC).isoformat()
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
        now = datetime.now(UTC).isoformat()
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
        now = datetime.now(UTC).isoformat()
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

    # -- Code intelligence (v0.58.0) --

    def ensure_code_file(
        self,
        path: str,
        project_id: int,
        language: str,
        content_hash: str,
    ) -> str:
        now = datetime.now(UTC).isoformat()
        with self._session() as session:
            result = session.run(
                """
                MERGE (cf:CodeFile {path: $path, project_id: $pid})
                ON CREATE SET cf.uuid = $uuid, cf.language = $lang,
                              cf.content_hash = $hash,
                              cf.created_at = $now, cf.last_indexed = $now
                ON MATCH SET  cf.language = $lang, cf.content_hash = $hash,
                              cf.last_indexed = $now
                RETURN cf.uuid AS uuid
                """,
                path=path,
                pid=project_id,
                uuid=str(uuid.uuid4()),
                lang=language,
                hash=content_hash,
                now=now,
            )
            return result.single()["uuid"]

    def ensure_code_symbol(
        self,
        qualified_name: str,
        project_id: int,
        name: str,
        kind: str,
        file_path: str,
        start_line: int,
        end_line: int,
        signature: str = "",
        docstring: str | None = None,
        parent_name: str | None = None,
    ) -> str:
        now = datetime.now(UTC).isoformat()
        props = {
            "name": name,
            "kind": kind,
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "signature": signature,
            "updated_at": now,
        }
        if docstring is not None:
            props["docstring"] = docstring
        if parent_name is not None:
            props["parent_name"] = parent_name

        with self._session() as session:
            result = session.run(
                """
                MERGE (cs:CodeSymbol {qualified_name: $qname, file_path: $fpath, project_id: $pid})
                ON CREATE SET cs.uuid = $uuid, cs.created_at = $now, cs += $props
                ON MATCH SET  cs += $props
                RETURN cs.uuid AS uuid
                """,
                qname=qualified_name,
                fpath=file_path,
                pid=project_id,
                uuid=str(uuid.uuid4()),
                now=now,
                props=props,
            )
            return result.single()["uuid"]

    def link_file_contains_symbol(self, file_uuid: str, symbol_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (cf:CodeFile {uuid: $file_uuid})
                MATCH (cs:CodeSymbol {uuid: $symbol_uuid})
                MERGE (cf)-[:CONTAINS]->(cs)
                """,
                file_uuid=file_uuid,
                symbol_uuid=symbol_uuid,
            )

    def link_symbol_contains_symbol(self, parent_uuid: str, child_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (parent:CodeSymbol {uuid: $parent_uuid})
                MATCH (child:CodeSymbol {uuid: $child_uuid})
                MERGE (parent)-[:CONTAINS]->(child)
                """,
                parent_uuid=parent_uuid,
                child_uuid=child_uuid,
            )

    def link_file_imports_file(self, importer_uuid: str, imported_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (a:CodeFile {uuid: $importer})
                MATCH (b:CodeFile {uuid: $imported})
                MERGE (a)-[:IMPORTS]->(b)
                """,
                importer=importer_uuid,
                imported=imported_uuid,
            )

    def delete_code_file(self, file_uuid: str) -> int:
        """Delete a CodeFile and detach-delete all its CodeSymbol children."""
        with self._session() as session:
            result = session.run(
                """
                MATCH (cf:CodeFile {uuid: $uuid})
                OPTIONAL MATCH (cf)-[:CONTAINS]->(cs:CodeSymbol)
                DETACH DELETE cs, cf
                RETURN count(cs) + 1 AS deleted_count
                """,
                uuid=file_uuid,
            )
            row = result.single()
            return row["deleted_count"] if row else 0

    def get_code_file(self, path: str, project_id: int) -> dict | None:
        with self._session() as session:
            result = session.run(
                """
                MATCH (cf:CodeFile {path: $path, project_id: $pid})
                RETURN cf.uuid AS uuid, cf.path AS path, cf.language AS language,
                       cf.content_hash AS content_hash, cf.last_indexed AS last_indexed
                """,
                path=path,
                pid=project_id,
            )
            row = result.single()
            return dict(row) if row else None

    def get_code_files(self, project_id: int) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (cf:CodeFile {project_id: $pid})
                RETURN cf.uuid AS uuid, cf.path AS path, cf.language AS language,
                       cf.content_hash AS content_hash, cf.last_indexed AS last_indexed
                ORDER BY cf.path
                """,
                pid=project_id,
            )
            return [dict(r) for r in result]

    def batch_upsert_code_graph(  # type: ignore[override]
        self,
        project_id: int,
        files: list[dict],
        import_edges: list[tuple[str, str]],
        stale_file_uuids: list[str],
        call_edges: list[dict] | None = None,
        chunk_size: int = 50,
    ) -> dict[str, str]:
        """Batch-upsert files, symbols, and edges in chunked transactions.

        Splits work into chunks of `chunk_size` files per transaction to avoid
        blowing Neo4j's transaction memory limit on large codebases.
        """
        now = datetime.now(UTC).isoformat()
        path_to_uuid: dict[str, str] = {}

        with self._session() as session:
            # 1) Delete stale files (separate transaction)
            if stale_file_uuids:
                for i in range(0, len(stale_file_uuids), chunk_size):
                    chunk = stale_file_uuids[i : i + chunk_size]
                    with session.begin_transaction() as tx:
                        tx.run(
                            """
                            UNWIND $uuids AS uid
                            MATCH (cf:CodeFile {uuid: uid})
                            OPTIONAL MATCH (cf)-[:CONTAINS]->(cs:CodeSymbol)
                            DETACH DELETE cs, cf
                            """,
                            uuids=chunk,
                        )
                        tx.commit()

            # 2-5) Upsert files + symbols in chunks
            for i in range(0, len(files), chunk_size):
                file_chunk = files[i : i + chunk_size]
                with session.begin_transaction() as tx:
                    # Upsert files
                    file_rows = []
                    for f in file_chunk:
                        file_rows.append({
                            "path": f["path"],
                            "lang": f["language"],
                            "hash": f["content_hash"],
                            "uuid": str(uuid.uuid4()),
                        })
                    result = tx.run(
                        """
                        UNWIND $rows AS r
                        MERGE (cf:CodeFile {path: r.path, project_id: $pid})
                        ON CREATE SET cf.uuid = r.uuid, cf.language = r.lang,
                                      cf.content_hash = r.hash,
                                      cf.created_at = $now, cf.last_indexed = $now
                        ON MATCH SET  cf.language = r.lang, cf.content_hash = r.hash,
                                      cf.last_indexed = $now
                        RETURN cf.path AS path, cf.uuid AS uuid
                        """,
                        rows=file_rows,
                        pid=project_id,
                        now=now,
                    )
                    for record in result:
                        path_to_uuid[record["path"]] = record["uuid"]

                    # Delete old symbols for changed files
                    changed_paths = [f["path"] for f in file_chunk]
                    tx.run(
                        """
                        UNWIND $paths AS p
                        MATCH (cf:CodeFile {path: p, project_id: $pid})-[:CONTAINS]->(cs:CodeSymbol)
                        DETACH DELETE cs
                        """,
                        paths=changed_paths,
                        pid=project_id,
                    )

                    # Create symbols
                    sym_rows = []
                    for f in file_chunk:
                        for sym in f.get("symbols", []):
                            props = {
                                "name": sym["name"],
                                "kind": sym["kind"],
                                "file_path": f["path"],
                                "start_line": sym["start_line"],
                                "end_line": sym["end_line"],
                                "signature": sym.get("signature", ""),
                                "updated_at": now,
                            }
                            if sym.get("docstring") is not None:
                                props["docstring"] = sym["docstring"]
                            if sym.get("parent_name") is not None:
                                props["parent_name"] = sym["parent_name"]
                            if sym.get("complexity") is not None:
                                props["complexity"] = sym["complexity"]
                            sym_rows.append({
                                "qname": sym["qualified_name"],
                                "fpath": f["path"],
                                "uuid": str(uuid.uuid4()),
                                "props": props,
                            })

                    if sym_rows:
                        tx.run(
                            """
                            UNWIND $rows AS r
                            CREATE (cs:CodeSymbol {
                                qualified_name: r.qname,
                                file_path: r.fpath,
                                project_id: $pid,
                                uuid: r.uuid,
                                created_at: $now
                            })
                            SET cs += r.props
                            WITH cs
                            MATCH (cf:CodeFile {path: cs.file_path, project_id: $pid})
                            MERGE (cf)-[:CONTAINS]->(cs)
                            """,
                            rows=sym_rows,
                            pid=project_id,
                            now=now,
                        )

                        # Link parent->child symbols
                        parent_edges = []
                        for f in file_chunk:
                            for sym in f.get("symbols", []):
                                if sym.get("parent_name"):
                                    parent_edges.append({
                                        "parent_qname": sym["parent_name"],
                                        "child_qname": sym["qualified_name"],
                                        "fpath": f["path"],
                                    })
                        if parent_edges:
                            tx.run(
                                """
                                UNWIND $edges AS e
                                MATCH (parent:CodeSymbol {qualified_name: e.parent_qname,
                                                           file_path: e.fpath, project_id: $pid})
                                MATCH (child:CodeSymbol {qualified_name: e.child_qname,
                                                          file_path: e.fpath, project_id: $pid})
                                MERGE (parent)-[:CONTAINS]->(child)
                                """,
                                edges=parent_edges,
                                pid=project_id,
                            )

                    tx.commit()

            # 6) Link file-level imports (separate chunked transactions)
            if import_edges:
                edge_rows = [{"src": src, "dst": dst} for src, dst in import_edges]
                for i in range(0, len(edge_rows), chunk_size * 4):
                    edge_chunk = edge_rows[i : i + chunk_size * 4]
                    with session.begin_transaction() as tx:
                        tx.run(
                            """
                            UNWIND $edges AS e
                            MATCH (a:CodeFile {path: e.src, project_id: $pid})
                            MATCH (b:CodeFile {path: e.dst, project_id: $pid})
                            MERGE (a)-[:IMPORTS]->(b)
                            """,
                            edges=edge_chunk,
                            pid=project_id,
                        )
                        tx.commit()

            # 7) Link symbol-level CALLS edges (chunked transactions)
            if call_edges:
                for i in range(0, len(call_edges), chunk_size * 4):
                    edge_chunk = call_edges[i : i + chunk_size * 4]
                    with session.begin_transaction() as tx:
                        tx.run(
                            """
                            UNWIND $edges AS e
                            MATCH (caller:CodeSymbol {qualified_name: e.caller_qname,
                                                       file_path: e.caller_file,
                                                       project_id: $pid})
                            MATCH (callee:CodeSymbol {qualified_name: e.callee_qname,
                                                       file_path: e.callee_file,
                                                       project_id: $pid})
                            MERGE (caller)-[r:CALLS]->(callee)
                            ON CREATE SET r.line = e.line
                            """,
                            edges=edge_chunk,
                            pid=project_id,
                        )
                        tx.commit()

        return path_to_uuid

    def get_code_symbols(self, file_path: str, project_id: int) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (cs:CodeSymbol {file_path: $fpath, project_id: $pid})
                RETURN cs.uuid AS uuid, cs.name AS name, cs.qualified_name AS qualified_name,
                       cs.kind AS kind, cs.start_line AS start_line, cs.end_line AS end_line,
                       cs.signature AS signature, cs.docstring AS docstring,
                       cs.parent_name AS parent_name
                ORDER BY cs.start_line
                """,
                fpath=file_path,
                pid=project_id,
            )
            return [dict(r) for r in result]

    # -- Code intelligence queries (v0.58.0 Phase 3) --

    def get_file_dependents(self, path: str, project_id: int) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (dep:CodeFile)-[:IMPORTS]->(target:CodeFile {path: $path, project_id: $pid})
                RETURN dep.path AS path, dep.language AS language
                ORDER BY dep.path
                """,
                path=path,
                pid=project_id,
            )
            return [dict(r) for r in result]

    def get_file_dependencies(self, path: str, project_id: int) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (source:CodeFile {path: $path, project_id: $pid})-[:IMPORTS]->(dep:CodeFile)
                RETURN dep.path AS path, dep.language AS language
                ORDER BY dep.path
                """,
                path=path,
                pid=project_id,
            )
            return [dict(r) for r in result]

    def get_file_structure(self, path: str, project_id: int) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (cf:CodeFile {path: $path, project_id: $pid})-[:CONTAINS]->(cs:CodeSymbol)
                RETURN cs.name AS name, cs.qualified_name AS qualified_name,
                       cs.kind AS kind, cs.start_line AS start_line,
                       cs.end_line AS end_line, cs.signature AS signature,
                       cs.docstring AS docstring, cs.parent_name AS parent_name
                ORDER BY cs.start_line
                """,
                path=path,
                pid=project_id,
            )
            return [dict(r) for r in result]

    def get_impact_graph(
        self, path: str, project_id: int, max_depth: int = 3
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                f"""
                MATCH p = (affected:CodeFile)-[:IMPORTS*1..{int(max_depth)}]->(target:CodeFile {{path: $path, project_id: $pid}})
                WHERE affected.project_id = $pid AND affected <> target
                WITH affected, min(length(p)) AS depth
                RETURN affected.path AS path, affected.language AS language, depth
                ORDER BY depth, affected.path
                """,
                path=path,
                pid=project_id,
            )
            return [dict(r) for r in result]

    def search_code_symbols(
        self,
        query: str,
        project_id: int,
        kind: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        kind_clause = "AND node.kind = $kind" if kind else ""
        with self._session() as session:
            result = session.run(
                f"""
                CALL db.index.fulltext.queryNodes('code_symbol_name_ft', $q)
                YIELD node, score
                WHERE node.project_id = $pid {kind_clause}
                RETURN node.qualified_name AS qualified_name, node.name AS name,
                       node.kind AS kind, node.file_path AS file_path,
                       node.signature AS signature, score
                ORDER BY score DESC
                LIMIT $lim
                """,
                q=query,
                pid=project_id,
                kind=kind,
                lim=limit,
            )
            return [dict(r) for r in result]

    # -- Code intelligence: call graph queries (v0.71.0) --

    def get_callers(
        self, qualified_name: str, project_id: int, limit: int = 50,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (caller:CodeSymbol)-[r:CALLS]->(target:CodeSymbol
                    {qualified_name: $qname, project_id: $pid})
                RETURN caller.qualified_name AS caller_qname,
                       caller.file_path AS caller_file,
                       r.line AS line
                ORDER BY caller.file_path, r.line
                LIMIT $lim
                """,
                qname=qualified_name, pid=project_id, lim=limit,
            )
            return [dict(r) for r in result]

    def get_callees(
        self, qualified_name: str, project_id: int, limit: int = 50,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (caller:CodeSymbol {qualified_name: $qname, project_id: $pid})
                      -[r:CALLS]->(callee:CodeSymbol)
                RETURN callee.qualified_name AS callee_qname,
                       callee.file_path AS callee_file,
                       r.line AS line
                ORDER BY callee.file_path, r.line
                LIMIT $lim
                """,
                qname=qualified_name, pid=project_id, lim=limit,
            )
            return [dict(r) for r in result]

    def get_call_chain(
        self,
        start_qname: str,
        end_qname: str,
        project_id: int,
        max_depth: int = 5,
        limit: int = 20,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                f"""
                MATCH (s:CodeSymbol {{qualified_name: $start, project_id: $pid}}),
                      (e:CodeSymbol {{qualified_name: $end, project_id: $pid}})
                MATCH path = (s)-[:CALLS*1..{max_depth}]->(e)
                RETURN [n IN nodes(path) | n.qualified_name] AS chain,
                       length(path) AS length
                ORDER BY length ASC
                LIMIT $lim
                """,
                start=start_qname, end=end_qname, pid=project_id, lim=limit,
            )
            return [dict(r) for r in result]

    def get_dead_code(
        self, project_id: int, limit: int = 50,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (func:CodeSymbol {project_id: $pid})
                WHERE func.kind IN ['function', 'method']
                  AND NOT func.name IN ['main', '__init__', '__main__',
                      'setup', 'run', '__new__', '__del__', '__enter__',
                      '__exit__', '__str__', '__repr__', '__eq__', '__hash__']
                  AND NOT func.name STARTS WITH 'test_'
                  AND NOT func.name STARTS WITH '_test'
                WITH func
                OPTIONAL MATCH (caller:CodeSymbol)-[:CALLS]->(func)
                WITH func, count(caller) AS caller_count
                WHERE caller_count = 0
                RETURN func.qualified_name AS qualified_name,
                       func.file_path AS file_path,
                       func.kind AS kind,
                       func.start_line AS start_line
                ORDER BY func.file_path, func.start_line
                LIMIT $lim
                """,
                pid=project_id, lim=limit,
            )
            return [dict(r) for r in result]

    def get_most_complex(
        self, project_id: int, limit: int = 20,
    ) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (cs:CodeSymbol {project_id: $pid})
                WHERE cs.complexity IS NOT NULL AND cs.complexity > 1
                RETURN cs.qualified_name AS qualified_name,
                       cs.file_path AS file_path,
                       cs.kind AS kind,
                       cs.complexity AS complexity
                ORDER BY cs.complexity DESC
                LIMIT $lim
                """,
                pid=project_id, lim=limit,
            )
            return [dict(r) for r in result]

    # -- Code intelligence: knowledge-code bridging (v0.58.0 Phase 7) --

    def link_entity_to_code_file(self, entity_uuid: str, file_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (e:Entity {uuid: $entity_uuid}), (cf:CodeFile {uuid: $file_uuid})
                MERGE (e)-[:REFERENCED_IN]->(cf)
                """,
                entity_uuid=entity_uuid,
                file_uuid=file_uuid,
            )

    def link_entity_to_code_symbol(self, entity_uuid: str, symbol_uuid: str) -> None:
        with self._session() as session:
            session.run(
                """
                MATCH (e:Entity {uuid: $entity_uuid}), (cs:CodeSymbol {uuid: $symbol_uuid})
                MERGE (e)-[:REFERENCED_IN]->(cs)
                """,
                entity_uuid=entity_uuid,
                symbol_uuid=symbol_uuid,
            )

    def get_code_for_entity(self, entity_uuid: str) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity {uuid: $entity_uuid})-[:REFERENCED_IN]->(target)
                WHERE target:CodeFile OR target:CodeSymbol
                RETURN labels(target)[0] AS type, target.path AS path,
                       target.qualified_name AS qualified_name, target.name AS name
                """,
                entity_uuid=entity_uuid,
            )
            return [dict(r) for r in result]

    def get_entities_for_code(self, file_path: str, project_id: int) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity)-[:REFERENCED_IN]->(cf:CodeFile {path: $path, project_id: $pid})
                RETURN e.uuid AS uuid, e.name AS name, e.entity_type AS entity_type
                UNION
                MATCH (e:Entity)-[:REFERENCED_IN]->(cs:CodeSymbol {file_path: $path, project_id: $pid})
                RETURN e.uuid AS uuid, e.name AS name, e.entity_type AS entity_type
                """,
                path=file_path,
                pid=project_id,
            )
            return [dict(r) for r in result]

    # -- Code intelligence: REFERENCED_IN bridging (v0.58.1) --

    def bridge_entities_to_symbols_batch(self, project_id: int) -> int:
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity {project_id: $pid}), (cs:CodeSymbol {project_id: $pid})
                WHERE toLower(e.name) = toLower(cs.name)
                MERGE (e)-[:REFERENCED_IN]->(cs)
                RETURN count(*) AS cnt
                """,
                pid=project_id,
            )
            return result.single()["cnt"]

    def bridge_entities_to_files_batch(self, project_id: int) -> int:
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity {project_id: $pid}), (cf:CodeFile {project_id: $pid})
                WHERE e.name CONTAINS '.' AND cf.path ENDS WITH ('/' + e.name)
                MERGE (e)-[:REFERENCED_IN]->(cf)
                RETURN count(*) AS cnt
                """,
                pid=project_id,
            )
            return result.single()["cnt"]

    def bridge_entity_names_to_symbols(self, names: list[str], project_id: int) -> int:
        if not names:
            return 0
        lower_names = [n.lower() for n in names]
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity {project_id: $pid}), (cs:CodeSymbol {project_id: $pid})
                WHERE toLower(e.name) IN $names AND toLower(e.name) = toLower(cs.name)
                MERGE (e)-[:REFERENCED_IN]->(cs)
                RETURN count(*) AS cnt
                """,
                pid=project_id,
                names=lower_names,
            )
            return result.single()["cnt"]

    def bridge_entity_names_to_files(self, names: list[str], project_id: int) -> int:
        if not names:
            return 0
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:Entity {project_id: $pid}), (cf:CodeFile {project_id: $pid})
                WHERE e.name IN $names AND e.name CONTAINS '.' AND cf.path ENDS WITH ('/' + e.name)
                MERGE (e)-[:REFERENCED_IN]->(cf)
                RETURN count(*) AS cnt
                """,
                pid=project_id,
                names=names,
            )
            return result.single()["cnt"]

    # -- Code intelligence: cross-project (v0.58.0 Phase 7) --

    def search_code_symbols_cross_project(
        self,
        query: str,
        project_ids: list[int],
        kind: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        kind_clause = "AND node.kind = $kind" if kind else ""
        with self._session() as session:
            result = session.run(
                f"""
                CALL db.index.fulltext.queryNodes('code_symbol_name_ft', $q)
                YIELD node, score
                WHERE node.project_id IN $pids {kind_clause}
                RETURN node.qualified_name AS qualified_name, node.name AS name,
                       node.kind AS kind, node.file_path AS file_path,
                       node.signature AS signature, node.project_id AS project_id, score
                ORDER BY score DESC
                LIMIT $lim
                """,
                q=query,
                pids=project_ids,
                kind=kind,
                lim=limit,
            )
            return [dict(r) for r in result]

    def get_shared_dependencies(self, project_ids: list[int]) -> list[dict]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (cf:CodeFile)
                WHERE cf.project_id IN $pids
                WITH cf.path AS path, collect(DISTINCT cf.project_id) AS pids
                WHERE size(pids) > 1
                RETURN path, pids AS project_ids, size(pids) AS count
                ORDER BY count DESC
                """,
                pids=project_ids,
            )
            return [dict(r) for r in result]
