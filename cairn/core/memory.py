"""Core memory operations: store, retrieve, modify."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cairn.core.analytics import track_operation
from cairn.core.constants import (
    AUTO_SUMMARIZE_EMBED_THRESHOLD,
    CONTRADICTION_ESCALATION_THRESHOLD,
    EPHEMERAL_MEMORY_TYPES,
    GRADUATION_TYPE_MAP,
    MemoryAction,
    WM_DEFAULT_SALIENCE,
    WM_SALIENCE_BOOST_FLOOR,
    WM_SALIENCE_DECAY_RATE,
)
from cairn.core.utils import extract_json, get_or_create_project
from cairn.embedding.interface import EmbeddingInterface
from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.config import LLMCapabilities
    from cairn.core.enrichment import Enricher
    from cairn.core.event_bus import EventBus
    from cairn.core.extraction import KnowledgeExtractor
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)


class MemoryStore:
    """Handles all memory CRUD operations."""

    def __init__(
        self, db: Database, embedding: EmbeddingInterface, *,
        enricher: Enricher | None = None,
        llm: LLMInterface | None = None,
        capabilities: LLMCapabilities | None = None,
        knowledge_extractor: KnowledgeExtractor | None = None,
        event_bus: EventBus | None = None,
    ):
        self.db = db
        self.embedding = embedding
        self.enricher = enricher
        self.llm = llm
        self.capabilities = capabilities
        self.knowledge_extractor = knowledge_extractor
        self.event_bus = event_bus

    def _publish(
        self, event_type: str, memory_id: int | None = None,
        project_id: int | None = None, session_name: str | None = None,
        **payload_fields,
    ) -> None:
        """Publish a memory event if event_bus is available."""
        if not self.event_bus:
            return
        # Ensure memory_id is in the payload for handlers
        if memory_id is not None:
            payload_fields.setdefault("memory_id", memory_id)
        project_name = None
        if project_id:
            row = self.db.execute_one("SELECT name FROM projects WHERE id = %s", (project_id,))
            if row:
                project_name = row["name"]
        try:
            self.event_bus.publish(
                session_name=session_name or "",
                event_type=event_type,
                project=project_name,
                payload=payload_fields if payload_fields else None,
            )
        except Exception:
            logger.warning("Failed to publish %s for memory %s", event_type, memory_id, exc_info=True)

    @track_operation("store")
    def store(
        self,
        content: str,
        project: str,
        memory_type: str = "note",
        importance: float = 0.5,
        tags: list[str] | None = None,
        session_name: str | None = None,
        related_files: list[str] | None = None,
        related_ids: list[int] | None = None,
        source_doc_id: int | None = None,
        file_hashes: dict[str, str] | None = None,
        enrich: bool = True,
        author: str | None = None,
        event_at: str | None = None,
        valid_until: str | None = None,
        salience: float | None = None,
        pinned: bool = False,
    ) -> dict:
        """Store a memory with embedding.

        Args:
            enrich: When False, skips LLM enrichment and relationship extraction.
                    Embedding is always generated. Use for bulk/chunk ingestion.

        Returns the stored memory dict with ID.
        """
        project_id = get_or_create_project(self.db, project)

        # Generate embedding (always — required for search)
        vector = self.embedding.embed(content)

        # --- Knowledge Extraction path (combined extraction + enrichment) ---
        use_extraction = (
            enrich
            and self.knowledge_extractor is not None
            and self.capabilities is not None
            and self.capabilities.knowledge_extraction
        )
        extraction_result = None
        if use_extraction:
            assert self.knowledge_extractor is not None
            try:
                # Fetch known entities for canonicalization
                known_entities = None
                try:
                    known_entities = self.knowledge_extractor.graph.get_known_entities(
                        project_id, limit=200,
                    )
                except Exception:
                    logger.debug("Failed to fetch known entities for canonicalization", exc_info=True)

                extraction_result = self.knowledge_extractor.extract(
                    content, author=author, known_entities=known_entities,
                )
            except Exception:
                logger.warning("Knowledge extraction failed, falling back to enrichment", exc_info=True)

        # --- Enrichment (skip for chunks/bulk, or when extraction succeeded) ---
        enrichment: dict = {}
        enrichment_status = "none"  # default for enrich=False
        if extraction_result is not None:
            assert self.knowledge_extractor is not None
            enrichment = self.knowledge_extractor.extract_enrichment_fields(extraction_result)
            enrichment_status = "complete"
        elif enrich and self.enricher:
            enrichment = self.enricher.enrich(content)
            enrichment_status = enrichment.pop("_status", "pending")
        elif enrich:
            enrichment_status = "pending"  # enricher not available

        # Override logic: caller-provided values win
        # Tags: caller tags stay in `tags`, LLM tags go to `auto_tags`
        auto_tags = enrichment.get("tags", [])
        caller_tags = tags or []

        # Importance: caller wins if not the default 0.5
        final_importance = importance
        if importance == 0.5 and "importance" in enrichment:
            final_importance = enrichment["importance"]

        # Memory type: caller wins if not the default "note"
        final_type = memory_type
        if memory_type == "note" and "memory_type" in enrichment:
            final_type = enrichment["memory_type"]

        # Summary: from LLM if enriched, otherwise first 200 chars
        summary = enrichment.get("summary")
        if not enrich and not summary:
            summary = content[:200].strip()

        # Entities: from LLM enrichment
        entities = enrichment.get("entities", [])

        # Content size management: re-embed using summary for large content
        if len(content) > AUTO_SUMMARIZE_EMBED_THRESHOLD:
            if summary:
                vector = self.embedding.embed(summary)
                logger.info("Large content (%d chars) — embedded summary instead", len(content))
            else:
                # No summary available (enrich=False, no enricher) — use truncated content
                summary = content[:500].strip() + "..."
                vector = self.embedding.embed(content[:2000])
                logger.info("Large content (%d chars) — embedded truncated content", len(content))

        # Auto-salience for ephemeral types
        if final_type in EPHEMERAL_MEMORY_TYPES and salience is None:
            salience = WM_DEFAULT_SALIENCE.get(final_type, 0.6)
        if salience is not None:
            salience = max(0.0, min(1.0, salience))

        # Insert memory
        import json as _json
        file_hashes_json = _json.dumps(file_hashes) if file_hashes else "{}"

        # RBAC: set owner_user_id from current user context (ca-124)
        from cairn.core.user import current_user as _current_user
        _user_ctx = _current_user()
        _owner_user_id = _user_ctx.user_id if _user_ctx else None

        # Parse temporal fields
        _event_at = None
        _valid_until = None
        if event_at:
            from datetime import datetime as _dt
            try:
                _event_at = _dt.fromisoformat(event_at)
            except (ValueError, TypeError):
                pass
        if valid_until:
            from datetime import datetime as _dt
            try:
                _valid_until = _dt.fromisoformat(valid_until)
            except (ValueError, TypeError):
                pass

        row = self.db.execute_one(
            """
            INSERT INTO memories
                (content, memory_type, importance, project_id, session_name,
                 embedding, tags, auto_tags, summary, related_files, source_doc_id,
                 file_hashes, entities, author,
                 enrichment_status, enriched_at,
                 owner_user_id, event_at, valid_until,
                 salience, pinned)
            VALUES
                (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s,
                 %s::jsonb, %s, %s,
                 %s, CASE WHEN %s IN ('complete', 'partial') THEN NOW() ELSE NULL END,
                 %s, %s, %s,
                 %s, %s)
            RETURNING id, created_at
            """,
            (
                content,
                final_type,
                final_importance,
                project_id,
                session_name,
                str(vector),
                caller_tags,
                auto_tags,
                summary,
                related_files or [],
                source_doc_id,
                file_hashes_json,
                entities,
                author,
                enrichment_status,
                enrichment_status,
                _owner_user_id,
                _event_at,
                _valid_until,
                salience,
                pinned,
            ),
        )

        assert row is not None
        memory_id = row["id"]

        # Create caller-specified relationships (part of core write)
        if related_ids:
            for related_id in related_ids:
                self.db.execute(
                    """
                    INSERT INTO memory_relations (source_id, target_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (memory_id, related_id),
                )

        # Phase 1 commit: core memory is now safely persisted.
        # Enrichment operations (graph persist, relationship extraction, etc.)
        # run asynchronously via event handler when event_bus is available,
        # or inline in a separate transaction as fallback.
        self.db.commit()
        logger.info("Stored memory #%d (type=%s, project=%s, enrich=%s)", memory_id, final_type, project, enrich)

        # Publish memory.created event — enables async enrichment + subscribers
        self._publish(
            "memory.created",
            memory_id=memory_id,
            project_id=project_id,
            session_name=session_name,
            memory_type=final_type,
            enrich=enrich,
            **({"extraction_result": extraction_result.model_dump()} if extraction_result else {}),
        )

        # Phase 2: best-effort enrichment
        # When event_bus is wired, the MemoryEnrichmentListener handles this
        # asynchronously with retry. Otherwise, run inline for backward compat.
        enrichment_result = {}
        if not self.event_bus:
            enrichment_result = self._post_store_enrichment(
                memory_id=memory_id,
                project_id=project_id,
                extraction_result=extraction_result,
                enrich=enrich,
                content=content,
                vector=vector,
                session_name=session_name,
                entities=entities,
                final_type=final_type,
                project=project,
            )

        result = {
            "id": memory_id,
            "content": content,
            "memory_type": final_type,
            "importance": final_importance,
            "project": project,
            "tags": caller_tags,
            "auto_tags": auto_tags,
            "summary": summary,
            "author": author,
            "auto_relations": enrichment_result.get("auto_relations", []),
            "conflicts": enrichment_result.get("conflicts", []),
            "rule_conflicts": enrichment_result.get("rule_conflicts"),
            "created_at": row["created_at"].isoformat(),
        }
        if salience is not None:
            result["salience"] = salience
            result["pinned"] = pinned
        if enrichment_result.get("graph_stats"):
            result["graph"] = enrichment_result["graph_stats"]
        return result

    def re_enrich(self, memory_id: int) -> dict:
        """Re-run enrichment for a specific memory.

        Useful for recovering from failed/partial enrichment.
        Returns updated enrichment data.
        """
        row = self.db.execute_one(
            """
            SELECT m.id, m.content, m.importance, m.memory_type,
                   m.project_id, m.session_name, m.embedding,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE m.id = %s AND m.is_active = true
            """,
            (memory_id,),
        )
        if not row:
            return {"error": f"Memory #{memory_id} not found or inactive"}

        if not self.enricher:
            return {"error": "Enricher not available"}

        enrichment = self.enricher.enrich(row["content"])
        enrichment_status = enrichment.pop("_status", "failed")

        updates = ["enrichment_status = %s"]
        update_params: list = [enrichment_status]

        if enrichment_status in ("complete", "partial"):
            updates.append("enriched_at = NOW()")

        entities = enrichment.get("entities", [])
        if entities:
            updates.append("entities = %s")
            update_params.append(entities)

        auto_tags = enrichment.get("tags", [])
        if auto_tags:
            updates.append("auto_tags = %s")
            update_params.append(auto_tags)

        summary = enrichment.get("summary")
        if summary:
            updates.append("summary = %s")
            update_params.append(summary)

        updates.append("updated_at = NOW()")
        update_params.append(memory_id)

        self.db.execute(
            f"UPDATE memories SET {', '.join(updates)} WHERE id = %s",
            tuple(update_params),
        )
        self.db.commit()

        logger.info("Re-enriched memory #%d: status=%s, entities=%d",
                     memory_id, enrichment_status, len(entities))

        return {
            "id": memory_id,
            "enrichment_status": enrichment_status,
            "entities": entities,
            "auto_tags": auto_tags,
        }

    def _post_store_enrichment(
        self,
        memory_id: int,
        project_id: int,
        extraction_result,
        enrich: bool,
        content: str,
        vector: list[float],
        session_name: str | None,
        entities: list[str],
        final_type: str,
        project: str,
    ) -> dict:
        """Phase 2: best-effort enrichment after PG commit.

        Runs graph persist (extraction path) or relationship extraction +
        temporal/co-occurrence edges (legacy path). Called inline when no
        event_bus, or by MemoryEnrichmentListener asynchronously.
        """
        auto_relations = []
        conflicts = []
        rule_conflicts = None
        graph_stats = None

        try:
            if extraction_result is not None:
                assert self.knowledge_extractor is not None
                try:
                    graph_stats = self.knowledge_extractor.resolve_and_persist(
                        extraction_result, memory_id, project_id,
                    )
                    logger.info(
                        "Graph persist: %d entities created, %d merged, %d statements, %d contradictions",
                        graph_stats.get("entities_created", 0),
                        graph_stats.get("entities_merged", 0),
                        graph_stats.get("statements_created", 0),
                        graph_stats.get("contradictions_found", 0),
                    )

                    try:
                        resolved = self.knowledge_extractor.resolve_dangling_objects(project_id)
                        if resolved > 0:
                            graph_stats["objects_resolved"] = resolved
                    except Exception:
                        logger.debug("Dangling object resolution failed (non-blocking)", exc_info=True)

                    # Bridge entities to code (non-blocking, best-effort)
                    try:
                        if (
                            self.capabilities is not None
                            and self.capabilities.code_intelligence
                            and extraction_result.entities
                        ):
                            from cairn.code.bridge import CodeBridgeService
                            bridge_svc = CodeBridgeService(self.knowledge_extractor.graph)
                            entity_names = [e.name for e in extraction_result.entities]
                            bridge_stats = bridge_svc.bridge_entity_names(entity_names, project_id)
                            if bridge_stats["total"] > 0:
                                graph_stats["code_bridge"] = bridge_stats
                    except Exception:
                        logger.debug("Code bridge after enrichment failed (non-blocking)", exc_info=True)

                except Exception:
                    logger.warning("Graph persist failed (non-blocking)", exc_info=True)

                if final_type == "rule":
                    rule_conflicts = self._check_rule_conflicts(content, project)

            elif enrich:
                auto_relations = self._extract_relationships(memory_id, content, vector, project_id)

                if session_name:
                    self._create_temporal_edge(memory_id, session_name, project_id)

                if entities and len(entities) >= 2:
                    self._create_entity_cooccurrence_edges(memory_id, entities, project_id)

                conflicts = self._escalate_contradictions(auto_relations)

                if final_type == "rule":
                    rule_conflicts = self._check_rule_conflicts(content, project)

            self.db.commit()
        except Exception:
            logger.warning("Enrichment transaction failed (memory #%d safe)", memory_id, exc_info=True)
            try:
                self.db.rollback()
            except Exception:
                pass

        return {
            "auto_relations": auto_relations,
            "conflicts": conflicts,
            "rule_conflicts": rule_conflicts,
            "graph_stats": graph_stats,
        }

    def _extract_relationships(
        self, memory_id: int, content: str, embedding: list[float], project_id: int,
    ) -> list[dict]:
        """Find and create relationships with similar existing memories via LLM.

        Returns list of created relations, or empty list on failure/disabled.
        """
        can_extract = (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.relationship_extract
        )
        if not can_extract:
            return []

        try:
            # Vector search for top 15 nearest neighbors (excluding self)
            # Wider horizon (was 5-NN) gives the LLM more candidates for
            # relationship extraction and produces a denser graph for
            # spreading activation.
            neighbors = self.db.execute(
                """
                SELECT m.id, m.content, m.summary
                FROM memories m
                WHERE m.id != %s AND m.is_active = true AND m.embedding IS NOT NULL
                ORDER BY m.embedding <=> %s::vector
                LIMIT 15
                """,
                (memory_id, str(embedding)),
            )

            if not neighbors:
                return []

            candidates = [
                {"id": n["id"], "summary": n.get("summary") or n["content"][:300]}
                for n in neighbors
            ]

            from cairn.llm.prompts import build_relationship_extraction_messages
            messages = build_relationship_extraction_messages(content, candidates)
            assert self.llm is not None
            raw = self.llm.generate(messages, max_tokens=512)
            relations = extract_json(raw, json_type="array")

            if not relations or not isinstance(relations, list):
                return []

            valid_relation_types = {"extends", "contradicts", "implements", "depends_on", "related"}
            created = []
            for rel in relations:
                if not isinstance(rel, dict):
                    continue
                rel_id = rel.get("id")
                rel_type = rel.get("relation", "related")
                if rel_id is None or rel_type not in valid_relation_types:
                    continue
                # Verify the ID is in our candidate set
                candidate_ids = {c["id"] for c in candidates}
                if rel_id not in candidate_ids:
                    continue

                self.db.execute(
                    """
                    INSERT INTO memory_relations (source_id, target_id, relation)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (memory_id, rel_id, rel_type),
                )
                created.append({"id": rel_id, "relation": rel_type})

            return created

        except Exception:
            logger.warning("Relationship extraction failed", exc_info=True)
            return []

    def _create_temporal_edge(self, memory_id: int, session_name: str, project_id: int) -> None:
        """Create a temporal edge to the previous memory in the same session.

        Links sequential memories within a session for spreading activation.
        """
        try:
            prev = self.db.execute_one(
                """
                SELECT id FROM memories
                WHERE session_name = %s AND project_id = %s AND id < %s
                    AND is_active = true
                ORDER BY id DESC LIMIT 1
                """,
                (session_name, project_id, memory_id),
            )
            if prev:
                self.db.execute(
                    """
                    INSERT INTO memory_relations (source_id, target_id, relation, edge_weight)
                    VALUES (%s, %s, 'temporal', 0.8)
                    ON CONFLICT DO NOTHING
                    """,
                    (prev["id"], memory_id),
                )
        except Exception:
            logger.debug("Temporal edge creation failed", exc_info=True)

    def _create_entity_cooccurrence_edges(
        self, memory_id: int, entities: list[str], project_id: int,
    ) -> None:
        """Create edges to memories sharing 2+ entities.

        Finds other memories in the same project with overlapping entities
        and creates 'related' edges between them.
        """
        try:
            # Find memories with overlapping entities (at least 2 in common)
            rows = self.db.execute(
                """
                SELECT m.id,
                       (SELECT COUNT(*) FROM unnest(m.entities) e
                        WHERE e = ANY(%s)) as overlap_count
                FROM memories m
                WHERE m.id != %s AND m.project_id = %s AND m.is_active = true
                    AND m.entities != '{}'
                HAVING (SELECT COUNT(*) FROM unnest(m.entities) e
                        WHERE e = ANY(%s)) >= 2
                ORDER BY overlap_count DESC
                LIMIT 10
                """,
                (entities, memory_id, project_id, entities),
            )
            for r in rows:
                self.db.execute(
                    """
                    INSERT INTO memory_relations (source_id, target_id, relation, edge_weight)
                    VALUES (%s, %s, 'related', 0.6)
                    ON CONFLICT DO NOTHING
                    """,
                    (memory_id, r["id"]),
                )
        except Exception:
            logger.debug("Entity co-occurrence edge creation failed", exc_info=True)

    def _escalate_contradictions(self, auto_relations: list[dict]) -> list[dict]:
        """Check auto_relations for contradicts entries against high-importance memories.

        Returns a list of conflict dicts for contradicted memories above the
        importance threshold, or an empty list.
        """
        contradicted_ids = [
            r["id"] for r in auto_relations if r.get("relation") == "contradicts"
        ]
        if not contradicted_ids:
            return []

        placeholders = ",".join(["%s"] * len(contradicted_ids))
        rows = self.db.execute(
            f"""
            SELECT id, summary, importance, memory_type
            FROM memories
            WHERE id IN ({placeholders})
            """,
            tuple(contradicted_ids),
        )

        conflicts = []
        for r in rows:
            if r["importance"] >= CONTRADICTION_ESCALATION_THRESHOLD:
                conflicts.append({
                    "id": r["id"],
                    "summary": r["summary"] or f"Memory #{r['id']}",
                    "importance": float(r["importance"]),
                    "action": "Consider inactivating — may be superseded by this memory",
                })
        return conflicts

    def _check_rule_conflicts(self, content: str, project: str) -> list[dict] | None:
        """Check a new rule against existing rules for conflicts via LLM.

        Returns list of conflicts, None if disabled/unavailable, or empty list if no conflicts.
        """
        can_check = (
            self.llm is not None
            and self.capabilities is not None
            and self.capabilities.rule_conflict_check
        )
        if not can_check:
            return None

        try:
            existing = self.get_rules(project)
            existing_rules = existing.get("items", [])

            if not existing_rules:
                return []

            from cairn.llm.prompts import build_rule_conflict_messages
            messages = build_rule_conflict_messages(content, existing_rules)
            assert self.llm is not None
            raw = self.llm.generate(messages, max_tokens=512)
            conflicts = extract_json(raw, json_type="array")

            if not conflicts or not isinstance(conflicts, list):
                return []

            # Validate conflict entries
            valid = []
            for c in conflicts:
                if not isinstance(c, dict):
                    continue
                if "rule_id" in c and "conflict" in c:
                    valid.append({
                        "rule_id": c["rule_id"],
                        "conflict": c["conflict"],
                        "severity": c.get("severity", "medium"),
                    })
            return valid

        except Exception:
            logger.warning("Rule conflict check failed", exc_info=True)
            return None

    @track_operation("recall")
    def recall(self, ids: list[int]) -> list[dict]:
        """Retrieve full content for one or more memory IDs."""
        if not ids:
            return []

        placeholders = ",".join(["%s"] * len(ids))

        # RBAC: scope to user's accessible projects (ca-124)
        from cairn.core.user import current_user as _current_user
        _user_ctx = _current_user()
        rbac_clause = ""
        rbac_params: tuple = ()
        if _user_ctx is not None and _user_ctx.role != "admin":
            rbac_clause = " AND m.project_id = ANY(%s)"
            rbac_params = (list(_user_ctx.project_ids),)

        rows = self.db.execute(
            f"""
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.related_files, m.is_active,
                   m.inactive_reason, m.session_name, m.entities, m.author,
                   m.created_at, m.updated_at,
                   m.salience, m.pinned,
                   p.name as project,
                   c.id as cluster_id, c.label as cluster_label,
                   c.member_count as cluster_size
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            LEFT JOIN cluster_members cm ON cm.memory_id = m.id
            LEFT JOIN clusters c ON c.id = cm.cluster_id
            WHERE m.id IN ({placeholders}){rbac_clause}
            ORDER BY m.id
            """,
            tuple(ids) + rbac_params,
        )

        # Fetch relations for all requested IDs in one query
        all_relations: dict[int, list[dict]] = {}
        if ids:
            rel_placeholders = ",".join(["%s"] * len(ids))
            rel_rows = self.db.execute(
                f"""
                SELECT mr.source_id, mr.target_id, mr.relation,
                       m.summary as target_summary, m.memory_type as target_type
                FROM memory_relations mr
                JOIN memories m ON m.id = mr.target_id
                WHERE mr.source_id IN ({rel_placeholders})
                UNION ALL
                SELECT mr.source_id, mr.target_id, mr.relation,
                       m.summary as target_summary, m.memory_type as target_type
                FROM memory_relations mr
                JOIN memories m ON m.id = mr.source_id
                WHERE mr.target_id IN ({rel_placeholders})
                """,
                tuple(ids) + tuple(ids),
            )
            for rr in rel_rows:
                for mid in ids:
                    if rr["source_id"] == mid:
                        all_relations.setdefault(mid, []).append({
                            "id": rr["target_id"],
                            "relation": rr["relation"] or "related",
                            "direction": "outgoing",
                            "summary": rr["target_summary"] or f"Memory #{rr['target_id']}",
                            "memory_type": rr["target_type"],
                        })
                    elif rr["target_id"] == mid:
                        all_relations.setdefault(mid, []).append({
                            "id": rr["source_id"],
                            "relation": rr["relation"] or "related",
                            "direction": "incoming",
                            "summary": rr["target_summary"] or f"Memory #{rr['source_id']}",
                            "memory_type": rr["target_type"],
                        })

        results = []
        for r in rows:
            entry = {
                "id": r["id"],
                "content": r["content"],
                "summary": r["summary"],
                "memory_type": r["memory_type"],
                "importance": r["importance"],
                "project": r["project"],
                "tags": r["tags"],
                "auto_tags": r["auto_tags"],
                "entities": r.get("entities", []),
                "related_files": r["related_files"],
                "is_active": r["is_active"],
                "inactive_reason": r["inactive_reason"],
                "session_name": r["session_name"],
                "author": r.get("author"),
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
                "cluster": None,
                "relations": all_relations.get(r["id"], []),
            }
            if r["cluster_id"] is not None:
                entry["cluster"] = {
                    "id": r["cluster_id"],
                    "label": r["cluster_label"],
                    "size": r["cluster_size"],
                }
            if r.get("salience") is not None:
                computed = self._compute_salience(
                    float(r["salience"]), r["updated_at"], r["pinned"],
                )
                entry["salience"] = round(computed, 3)
                entry["base_salience"] = float(r["salience"])
                entry["pinned"] = r["pinned"]
            results.append(entry)

        return results

    def _get_memory_project_id(self, memory_id: int) -> int | None:
        """Look up the project_id for a memory (for event publishing)."""
        row = self.db.execute_one(
            "SELECT project_id FROM memories WHERE id = %s", (memory_id,),
        )
        return row["project_id"] if row else None

    @track_operation("modify")
    def modify(
        self,
        memory_id: int,
        action: str,
        content: str | None = None,
        memory_type: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
        reason: str | None = None,
        project: str | None = None,
        author: str | None = None,
    ) -> dict:
        """Update, inactivate, or reactivate a memory."""
        # RBAC: check user has access to this memory's project (ca-124)
        from cairn.core.user import current_user as _current_user
        _user_ctx = _current_user()
        if _user_ctx is not None and _user_ctx.role != "admin":
            row = self.db.execute_one(
                "SELECT project_id FROM memories WHERE id = %s", (memory_id,),
            )
            if row and row["project_id"] not in _user_ctx.project_ids:
                return {"error": "Access denied", "id": memory_id}

        if action == MemoryAction.INACTIVATE:
            self.db.execute(
                """
                UPDATE memories
                SET is_active = false, inactive_reason = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (reason or "No reason provided", memory_id),
            )
            self.db.commit()
            self._publish(
                "memory.inactivated",
                memory_id=memory_id,
                project_id=self._get_memory_project_id(memory_id),
                reason=reason or "No reason provided",
            )
            return {"id": memory_id, "action": "inactivated"}

        if action == MemoryAction.REACTIVATE:
            self.db.execute(
                """
                UPDATE memories
                SET is_active = true, inactive_reason = NULL, updated_at = NOW()
                WHERE id = %s
                """,
                (memory_id,),
            )
            self.db.commit()
            self._publish(
                "memory.reactivated",
                memory_id=memory_id,
                project_id=self._get_memory_project_id(memory_id),
            )
            return {"id": memory_id, "action": "reactivated"}

        if action == MemoryAction.GRADUATE:
            # Read current state to get type for remapping
            current = self.db.execute_one(
                "SELECT memory_type, salience FROM memories WHERE id = %s AND is_active = true",
                (memory_id,),
            )
            if not current:
                return {"error": f"Memory #{memory_id} not found or inactive"}
            if current["salience"] is None:
                return {"error": f"Memory #{memory_id} is already crystallized (no salience)"}
            graduated_type = memory_type or GRADUATION_TYPE_MAP.get(current["memory_type"], current["memory_type"])
            self.db.execute(
                """
                UPDATE memories
                SET salience = NULL, pinned = FALSE, memory_type = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (graduated_type, memory_id),
            )
            self.db.commit()
            self._publish(
                "memory.graduated", memory_id=memory_id,
                project_id=self._get_memory_project_id(memory_id),
                from_type=current["memory_type"], to_type=graduated_type,
            )
            return {"id": memory_id, "action": "graduated", "memory_type": graduated_type}

        if action == MemoryAction.PIN:
            self.db.execute(
                "UPDATE memories SET pinned = TRUE, updated_at = NOW() WHERE id = %s AND is_active = true",
                (memory_id,),
            )
            self.db.commit()
            return {"id": memory_id, "action": "pinned"}

        if action == MemoryAction.UNPIN:
            current = self.db.execute_one(
                "SELECT salience, updated_at, pinned FROM memories WHERE id = %s AND is_active = true",
                (memory_id,),
            )
            if not current:
                return {"error": f"Memory #{memory_id} not found or inactive"}
            computed = self._compute_salience(
                float(current["salience"]) if current["salience"] is not None else 0.0,
                current["updated_at"], current["pinned"],
            )
            self.db.execute(
                "UPDATE memories SET pinned = FALSE, salience = %s, updated_at = NOW() WHERE id = %s",
                (computed, memory_id),
            )
            self.db.commit()
            return {"id": memory_id, "action": "unpinned", "salience": round(computed, 3)}

        if action == MemoryAction.BOOST:
            current = self.db.execute_one(
                "SELECT salience, updated_at, pinned, project_id FROM memories WHERE id = %s AND is_active = true",
                (memory_id,),
            )
            if not current:
                return {"error": f"Memory #{memory_id} not found or inactive"}
            if current["salience"] is None:
                return {"error": f"Memory #{memory_id} is crystallized (no salience to boost)"}
            computed = self._compute_salience(
                float(current["salience"]), current["updated_at"], current["pinned"],
            )
            new_salience = max(computed, WM_SALIENCE_BOOST_FLOOR)
            self.db.execute(
                "UPDATE memories SET salience = %s, updated_at = NOW() WHERE id = %s",
                (new_salience, memory_id),
            )
            self.db.commit()
            self._publish(
                "memory.boosted", memory_id=memory_id,
                project_id=current["project_id"], salience=new_salience,
            )
            return {"id": memory_id, "action": "boosted", "salience": round(new_salience, 3)}

        if action == MemoryAction.UPDATE:
            updates: list[str] = []
            params: list = []

            if content is not None:
                updates.append("content = %s")
                params.append(content)
                # Re-embed on content change
                vector = self.embedding.embed(content)
                updates.append("embedding = %s::vector")
                params.append(str(vector))

            if memory_type is not None:
                updates.append("memory_type = %s")
                params.append(memory_type)

            if importance is not None:
                updates.append("importance = %s")
                params.append(importance)

            if tags is not None:
                updates.append("tags = %s")
                params.append(tags)

            if project is not None:
                project_id = get_or_create_project(self.db, project)
                updates.append("project_id = %s")
                params.append(project_id)

            if author is not None:
                updates.append("author = %s")
                params.append(author)

            if not updates:
                return {"id": memory_id, "action": "no_changes"}

            updates.append("updated_at = NOW()")
            params.append(memory_id)

            self.db.execute(
                f"UPDATE memories SET {', '.join(updates)} WHERE id = %s",
                tuple(params),
            )
            self.db.commit()
            self._publish(
                "memory.updated",
                memory_id=memory_id,
                project_id=self._get_memory_project_id(memory_id),
                content_changed=content is not None,
            )
            return {"id": memory_id, "action": "updated"}

        raise ValueError(f"Unknown action: {action}")

    @track_operation("rules")
    def get_rules(
        self, project: str | list[str] | None = None,
        limit: int | None = None, offset: int = 0,
    ) -> dict:
        """Retrieve active rule-type memories for project(s) and __global__.

        When auth enabled: __global__ acts as __system__ (readable by all),
        plus per-user personal rules from __personal__:<username>.
        When auth disabled: __global__ as today — zero change.

        Returns dict with 'total', 'limit', 'offset', and 'items' keys.
        """
        if isinstance(project, list):
            project_names = list(set(project + ["__global__"]))
        else:
            project_names = ["__global__"] if not project else ["__global__", project]

        # RBAC: add personal rules project when auth is active (ca-124)
        from cairn.core.user import current_user as _current_user
        _user_ctx = _current_user()
        if _user_ctx is not None:
            personal_project = f"__personal__:{_user_ctx.username}"
            if personal_project not in project_names:
                project_names.append(personal_project)

        count_row = self.db.execute_one(
            """
            SELECT COUNT(*) as total FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE m.memory_type = 'rule' AND m.is_active = true
                AND p.name = ANY(%s)
            """,
            (project_names,),
        )
        assert count_row is not None
        total = count_row["total"]

        query = """
            SELECT m.id, m.content, m.importance, m.tags, m.created_at,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE m.memory_type = 'rule'
                AND m.is_active = true
                AND p.name = ANY(%s)
            ORDER BY m.importance DESC, m.created_at DESC
        """
        params: list = [project_names]

        if limit is not None:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])

        rows = self.db.execute(query, tuple(params))

        items = [
            {
                "id": r["id"],
                "content": r["content"],
                "importance": r["importance"],
                "project": r["project"],
                "tags": r["tags"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    # ------------------------------------------------------------------
    # Ephemeral memory support (formerly working memory)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_salience(
        base_salience: float,
        updated_at: datetime,
        pinned: bool,
    ) -> float:
        """Compute current salience with time-based decay.

        Decay formula: base * (0.97 ^ days_elapsed)
        Pinned items skip decay entirely.
        """
        if pinned:
            return base_salience

        now = datetime.now(UTC)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)

        elapsed = (now - updated_at).total_seconds() / 86400.0  # days
        if elapsed <= 0:
            return base_salience

        decayed = base_salience * math.pow(WM_SALIENCE_DECAY_RATE, elapsed)
        return max(0.0, min(1.0, decayed))

    @track_operation("orient_items")
    def orient_items(self, project: str, *, limit: int = 5) -> list[dict]:
        """Return top active ephemeral items for orient() injection.

        Compact format, sorted by computed salience (highest first).
        """
        from cairn.core.utils import get_project
        project_id = get_project(self.db, project)
        if project_id is None:
            return []

        rows = self.db.execute(
            """
            SELECT id, content, memory_type, salience, author, pinned,
                   updated_at, created_at
            FROM memories
            WHERE project_id = %s AND is_active = true AND salience IS NOT NULL
            ORDER BY salience DESC, created_at DESC
            LIMIT %s
            """,
            (project_id, limit * 2),  # fetch extra to account for post-decay filtering
        )

        items = []
        for r in rows:
            computed = self._compute_salience(
                float(r["salience"]), r["updated_at"], r["pinned"],
            )
            if computed < 0.05:  # skip nearly-faded items
                continue
            items.append({
                "id": r["id"],
                "item_type": r["memory_type"],
                "content": r["content"],
                "salience": round(computed, 3),
                "author": r["author"],
                "pinned": r["pinned"],
            })
            if len(items) >= limit:
                break

        return items

    def export_project(self, project: str) -> list[dict]:
        """Export all active memories for a project."""
        rows = self.db.execute(
            """
            SELECT m.id, m.content, m.summary, m.memory_type, m.importance,
                   m.tags, m.auto_tags, m.related_files, m.session_name,
                   m.created_at, m.updated_at,
                   p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE p.name = %s AND m.is_active = true
            ORDER BY m.created_at DESC
            """,
            (project,),
        )

        return [
            {
                "id": r["id"],
                "content": r["content"],
                "summary": r["summary"],
                "memory_type": r["memory_type"],
                "importance": r["importance"],
                "project": r["project"],
                "tags": r["tags"],
                "auto_tags": r["auto_tags"],
                "related_files": r["related_files"],
                "session_name": r["session_name"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]
