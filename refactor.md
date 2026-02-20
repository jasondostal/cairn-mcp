# Cairn Refactor Plan

**Created:** 2026-02-20
**Epic:** wi-0061
**Status:** DRAFT — awaiting Jason's review before any implementation

## Key Memories
- #323-329: LoCoMo diagnostic (11 search bugs, 8.6% real accuracy)
- #332: Memory lifecycle design (current broken flow vs target)
- #333: Event bus audit (split architecture — memories outside bus)
- #334: Full Potemkin Village audit findings (11 items)
- #335: CRITICAL CORRECTION — doc #44 (v2 plan) is irrelevant, do not use as authority

## WHY THIS EXISTS

LoCoMo benchmark: real search accuracy is 8.6% (not 18%). 11 bugs found.
Event bus handles work items but NOT memories. Ghost config flags. Features
with no callers. Orient trail returns config flag names as entities.

This file is the execution plan. It must survive context compaction.

---

## CRITICAL RULES

1. **NEVER use old plan documents (especially doc #44, the v0.27 "v2 plan")
   as authority for deleting features.** That plan is 27 versions old.
2. **Evaluate features on EVIDENCE:** benchmark data, production behavior,
   code examination. Not aspirational architecture docs.
3. **If a feature's replacement doesn't exist or is broken, DO NOT delete
   the original.** Fix the replacement first, prove it works, THEN evaluate.
4. **Run tests after every group of changes.**
5. **Working directly on main. Commit after each phase.**

---

## WHAT WE KNOW (from code examination, not from old plans)

### Confirmed by code agents (session 2026-02-20-88ac1772):

**Event Bus (memory #333):**
- Event bus is Postgres-backed, retry with backoff, SSE streaming. Works.
- ONE subscriber: GraphProjectionListener (work_item.*, task.*, thinking.*)
- store() does NOT publish events — extraction is inline, synchronous, no retry
- modify() does NOT publish events — Neo4j not cleaned up on inactivation
- search() does NOT publish events — no access tracking

**Store Pipeline (code agent):**
- Two-phase commit: Phase 1 = PG INSERT (ACID). Phase 2 = enrichment/graph (best effort)
- Extraction runs INLINE during store(), blocking the caller
- If Neo4j write fails, no retry. Memory exists in PG with no graph representation.
- Two enrichment paths: extraction (CAIRN_KNOWLEDGE_EXTRACTION) OR legacy enrichment
- Both are OFF in production for extraction, ON for legacy enrichment

**Search Pipeline (code agent, memories #323-329):**
- 11 bugs identified. 6 affect production:
  1. No similarity threshold on entity extraction (every word matches random entities)
  2. BFS fan-out returns 128 memories per entity (uncontrolled)
  3. No aspect filtering (all statements returned, not aspect-relevant)
  4. Wrong retrieval unit (memory blobs, not statement facts)
  5. Naive blend (graph fills all slots, RRF pushed past limit)
  9. SearchV2 graph-primary sabotages working RRF results
- 5 affect benchmark only: conversation scoping, Neo4j collision, query expansion, scorer, adversarial inflation

**Config Flags (code agent):**
- 68 total flags. All functional (code exists for each).
- 2 ghost flags: CAIRN_NARRATIVES, LLM_EVENT_DIGEST — config entries with NO code
- 1 proven harmful: QUERY_EXPANSION — Bug 8, "Caroline" → "Caroline Kennedy"
- 1 unwired feature: CONFIDENCE_GATING — implemented but never called from any path
  (Core/RedPlanet uses aggressive LLM-as-judge gating and gets 88%. Keep, evaluate by benchmark.)
- CAIRN_KNOWLEDGE_EXTRACTION and CAIRN_SEARCH_V2 both OFF in production

**Neo4j Methods (code agent):**
- 51 public methods. 10 never called (19.6%)
- 7 replaced by ensure_* pattern (create_work_item, update_work_item_status, etc.)
  The ensure pattern IS the replacement, it works, confirmed by graph_projection listener
- 3 are useful capabilities not yet wired (session_context, temporal_entities, link_thought_to_entities)

**Other findings:**
- Clustering: works, but LLM labeling silently fails → "Cluster 28" fallbacks
- Orient trail: returns ALL entity types including config flag names as "entities touched"
- Ingest pipeline: exists, HTTP-only, no MCP tool, not wired to store()
- Session synthesis: code exists, nothing calls it
- REST API vs MCP: same services underneath, some inconsistencies
- work_item_id: missing on 2 of 10 work_item events (blocked, unblocked)
- Broken test import in test_clustering.py

---

## PHASE 1: SAFE DELETIONS (evidence-based, no controversy)

These items have clear evidence for removal. No judgment calls.

### 1.1 Delete ghost config flags

**Evidence:** Code agents confirmed NO implementation exists for these flags.

- [x] Remove CAIRN_CAIRN_NARRATIVES from config.py (flag with no code)
- [x] Remove CAIRN_LLM_EVENT_DIGEST from config.py (flag with no code)

### 1.2 Delete query expansion

**Evidence:** LoCoMo Bug 8. Proven harmful — "Caroline" expands to "Caroline Kennedy",
poisoning search results. Currently OFF everywhere, no production impact.

- [x] Remove _expand_query() from search.py
- [x] Remove CAIRN_LLM_QUERY_EXPANSION flag from config.py
- [x] Remove all calls/checks for query_expansion (config, prompts, tests, UI, benchmark)

### 1.3 Delete replaced Neo4j methods

**Evidence:** ensure_* pattern replaced these. Graph projection listener uses ensure_*
exclusively. These methods have ZERO callers outside their own file.

Delete from neo4j_provider.py:
- [x] search_entities_fulltext() — 0 callers, vector search replaced it
- [x] create_work_item() — 0 callers, ensure_work_item() replaced it
- [x] update_work_item_status() — 0 callers, ensure_work_item() replaced it
- [x] complete_work_item() — 0 callers, ensure_work_item() replaced it
- [x] assign_work_item() — 0 callers, ensure_work_item() replaced it
- [x] update_work_item_gate() — 0 callers, gates are PG-only
- [x] resolve_work_item_gate() — 0 callers, gates are PG-only

DO NOT delete (useful capabilities, wire later):
- session_context(), temporal_entities(), link_thought_to_entities(), link_work_item_to_entity()

### 1.4 Fix broken clustering test import

- [x] Fix tests/test_clustering.py import of HDBSCAN_MIN_CLUSTER_SIZE

### 1.5 Fix work_item_id on blocked/unblocked events

- [x] Add work_item_id=blocker["id"] to _publish("work_item.blocked") in work_items.py
- [x] Add work_item_id=blocker["id"] to _publish("work_item.unblocked") in work_items.py

### 1.6 Fix orient trail entity filtering

- [x] Add entity_type filter to recent_activity() Cypher query in neo4j_provider.py
- [x] Filter to: Person, Organization, Project, Task, Event
- [x] Exclude: Concept, Technology (too noisy — config flags extracted as entities)

### 1.7 Phase 1 verification & commit

- [x] Run: python3 -m pytest -x -q (303 passed, 2 pre-existing failures unrelated)
- [x] Commit: 1465ae0 refactor: Phase 1 — remove dead code, ghost flags, fix small bugs

---

## PHASE 2: FIX SEARCH BUGS (the 6 production bugs)

These are bugs, not feature decisions. Fix regardless of anything else.
No benchmark needed — these are objectively broken.

### 2.1 Entity extraction threshold (Bug 1) — DONE

- [x] Added ENTITY_EXTRACTION_THRESHOLD = 0.7 to SearchV2 class
- [x] Added `threshold` parameter to GraphProvider.search_entities_by_embedding()
- [x] Neo4j Cypher: `AND score > $threshold` filters garbage matches
- [x] Previously: top-3 per query chunk with NO threshold → 20+ garbage entities

### 2.2 BFS fan-out control (Bug 2) — DONE

- [x] Hop 1 capped at 30 results per entity (HOP1_CAP_PER_ENTITY)
- [x] Hop 2 capped at 15 results per entity (HOP2_CAP_PER_ENTITY)
- [x] Previously: 128 memories per entity, no cap

### 2.3 Aspect filtering (Bug 3) — DEFERRED

Requires LLM-based query aspect classification. Needs design work —
the router would need to classify queries into aspects (Action, Belief,
Preference, etc.) before the handler can filter. Moving to Phase 6
for benchmark-guided evaluation.

### 2.4 Statement-level retrieval (Bug 4) — DEFERRED

Requires changing the entire return format from memory blobs to statement
facts. This is an architectural change that affects the MCP tool response
format and all downstream consumers. Moving to Phase 6 for benchmark-guided
evaluation.

### 2.5 Blend interleaving (Bugs 5 + 9) — DONE

- [x] _blend_results() now sorts by score so both sources compete equally
- [x] Updated tests to expect score-ordered behavior
- [x] Previously: graph filled all slots first, RRF buried past limit

### 2.6 Phase 2 verification

- [x] Run: python3 -m pytest -x -q (303 passed)
- [ ] Commit

---

## PHASE 3: UNIFY EVENT BUS

Move memory operations through the event bus (same pattern as work items).

### 3.1 Add memory events

- [ ] Publish memory.created after PG INSERT in memory.py
- [ ] Publish memory.updated after modify()
- [ ] Publish memory.inactivated after inactivation

### 3.2 Move extraction to event handler

- [ ] GraphProjectionListener subscribes to memory.* events
- [ ] Handler triggers extraction + Neo4j writes asynchronously
- [ ] Gets retry logic (5 attempts, exponential backoff) for free
- [ ] store() returns after PG INSERT + embedding (fast)

**Tradeoff:** store() currently returns extraction results (graph_stats, conflicts).
If async, these aren't available immediately. Caller (Claude Code) doesn't use
graph_stats — it uses memory ID and content, available from Phase 1 commit.

### 3.3 Add search.executed event

- [ ] Publish after search returns results
- [ ] Payload: query, result_count, memory_ids_returned
- [ ] Enables access tracking for decay/lifecycle

### 3.4 Wire session synthesis

- [ ] Subscribe to session_end event
- [ ] Call session_synthesizer.synthesize()
- [ ] Store result as memory (type: session_summary)

### 3.5 Phase 3 verification

- [ ] Store memory → check events table for memory.created
- [ ] Verify Neo4j populated asynchronously (may take seconds)
- [ ] Inactivate memory → verify Neo4j cleanup
- [ ] Verify store() returns faster
- [ ] Commit

---

## PHASE 4: FIX INGESTION + REMAINING ITEMS

### 4.1 Wire ingest pipeline as MCP tool

- [ ] Add @mcp.tool() def ingest() in server.py
- [ ] Chunks should flow through store() so extraction applies

### 4.2 Fix clustering labels

- [ ] Investigate why LLM labeling fails (prompt? backend? input?)
- [ ] Fix so clusters get real labels, not "Cluster 28"

### 4.3 Wire clusters into orient()

- [ ] Include cluster summaries in orient() boot response

### 4.4 Fix API inconsistencies

- [ ] REST /search: add budget enforcement (match MCP)
- [ ] /graph endpoint: use graph provider, not raw SQL

### 4.5 Delete session synthesis ghost wiring

- [ ] If wired in Phase 3, remove CAIRN_LLM_SESSION_SYNTHESIS flag
  (synthesis becomes event-driven, not flag-gated)

---

## PHASE 5: HARDEN

### 5.1 CI dead code detection
### 5.2 Config flag coverage tests
### 5.3 Benchmark regression gate
### 5.4 Enable features in production config

---

## PHASE 6: BENCHMARK EVALUATION (requires fast LoCoMo harness)

Deferred to last — each run takes ~7 hours currently. Jason has an agent
researching batch LoCoMo testing via Bedrock to speed this up.

These features exist, work, and might help. We need LoCoMo data before deciding.

### 6.1 Fix the scorer first

**Why:** Can't evaluate anything if the scorer is broken (Bug 10 — concatenated F1).

- [ ] Change eval/benchmark/rag.py evaluate_retrieval() to per-memory F1 (take max)
- [ ] Run LoCoMo baseline with fixed scorer to get real numbers

### 6.2 Ablation tests

Run LoCoMo with each feature toggled independently:

- [ ] Spreading activation ON vs OFF — does it help RRF?
- [ ] MCA gate ON vs OFF — does keyword coverage filtering help?
- [ ] Type routing ON vs OFF — does intent-based boosting help?
- [ ] Reranking ON vs OFF — does cross-encoder reranking help?
- [ ] Confidence gating ON vs OFF — does LLM quality assessment help?
  (Core/RedPlanet uses aggressive LLM-as-judge and gets 88%. We built it, never wired it.)
- [ ] SearchV2 ON vs OFF — does graph-primary help or hurt?

**Decision rule:** If a feature improves LoCoMo score, KEEP. If it hurts or is neutral, REMOVE.
No deleting based on vibes or old plans.

### 6.3 Document results and decide

- [ ] Record ablation results in a memory
- [ ] Update this file with deletion/keep decisions based on data
- [ ] Delete features proven harmful, keep features proven helpful

---

## PHASE STATUS

- [x] **Phase 1: Safe Deletions** — DONE (1465ae0)
- [~] **Phase 2: Fix Search Bugs** — DONE (bugs 1,2,5+9 fixed; bugs 3,4 deferred to Phase 6)
- [ ] Phase 3: Unify Event Bus — NOT STARTED
- [ ] Phase 4: Ingestion + Remaining — NOT STARTED
- [ ] Phase 5: Harden — NOT STARTED
- [ ] Phase 6: Benchmark Evaluation — BLOCKED (waiting on fast LoCoMo harness)

---

## FILES REFERENCE

| File | Purpose |
|------|---------|
| cairn/server.py | MCP tool definitions |
| cairn/core/memory.py | MemoryStore — store/recall/modify |
| cairn/core/search.py | RRF hybrid search (7 signals) |
| cairn/core/search_v2.py | Graph-primary search router |
| cairn/core/handlers.py | Search handlers (entity_lookup, aspect, etc.) |
| cairn/core/event_bus.py | EventBus pub/sub |
| cairn/core/event_dispatcher.py | Background dispatch worker |
| cairn/listeners/graph_projection.py | PG→Neo4j sync listener |
| cairn/core/extraction.py | LLM extraction + Neo4j writes |
| cairn/core/enrichment.py | Legacy enrichment |
| cairn/core/services.py | Service factory |
| cairn/core/constants.py | RRF weights, thresholds |
| cairn/config.py | All config flags |
| cairn/graph/neo4j_provider.py | Neo4j operations (51 methods) |
| cairn/core/activation.py | Spreading activation — KEEP, evaluate by benchmark |
| cairn/core/mca.py | MCA keyword gate — KEEP, evaluate by benchmark |
| cairn/core/synthesis.py | Session synthesis — orphaned, wire in Phase 4 |
| cairn/core/ingest.py | Ingest pipeline — wire MCP in Phase 5 |
| cairn/core/clustering.py | HDBSCAN clustering — fix labels |
| eval/benchmark/rag.py | Benchmark scorer — fix in Phase 6 |
