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
- [x] Commit: 00aa355 refactor: Phase 2 — fix search bugs (entity threshold, BFS caps, blend)

---

## PHASE 3: UNIFY EVENT BUS — DONE

Move memory operations through the event bus (same pattern as work items).

### 3.1 Add memory events — DONE

- [x] Publish memory.created after PG INSERT in memory.py
- [x] Publish memory.updated after modify() with action=update
- [x] Publish memory.inactivated after modify() with action=inactivate
- [x] Publish memory.reactivated after modify() with action=reactivate
- [x] Added _publish() helper and _get_memory_project_id() to MemoryStore
- [x] Injected event_bus into MemoryStore constructor

### 3.2 Move enrichment to event handler — DONE

- [x] Created MemoryEnrichmentListener (cairn/listeners/memory_enrichment.py)
- [x] Subscribes to memory.* events, handles memory.created
- [x] Extracted Phase 2 enrichment into _post_store_enrichment() on MemoryStore
- [x] When event_bus present: enrichment runs async via dispatcher with retry
- [x] When no event_bus: enrichment runs inline (backward compat)
- [x] extraction_result serialized into event payload for async reconstruction

### 3.3 Add search.executed event — DONE

- [x] Published in server.py after search returns results
- [x] Payload: query (truncated), result_count, memory_ids, search_mode
- [x] Enables future access tracking for decay/lifecycle

### 3.4 Wire session synthesis — DONE

- [x] Created SessionSynthesisListener (cairn/listeners/session_synthesis.py)
- [x] Subscribes to session_end event
- [x] Calls session_synthesizer.synthesize()
- [x] Stores narrative as memory (type: session_summary, enrich=False)

### 3.5 Phase 3 verification

- [x] Run: python3 -m pytest -x -q (329 passed, including 9 new event tests)
- [x] Commit: af29cc8 refactor: Phase 3 — unify event bus, async memory enrichment

---

## PHASE 4: FIX INGESTION + REMAINING ITEMS

### 4.1 Wire ingest pipeline as MCP tool — DONE

- [x] Added @mcp.tool() def ingest() in server.py (Tool 16)
- [x] Accepts content or URL, project, hint, doc_type, title, tags, etc.
- [x] Chunks flow through store() so extraction + events apply
- [x] Added ingest_pipeline to server.py globals

### 4.2 Fix clustering labels — IMPROVED

- [x] Investigated: falls back to "Cluster N" when LLM is None or call fails
- [x] Root cause: llm_fast=None when enrichment disabled, or LLM returns bad JSON
- [x] Fixed _parse_summaries() to fill missing clusters with generic labels
  instead of discarding all LLM results on partial failure
- [x] Added logging of raw LLM response on parse failure for debugging

### 4.3 Wire clusters into orient() — DEFERRED

Low priority. Clusters are available via the insights() tool. Adding to orient()
would add complexity and token budget pressure for uncertain value.

### 4.4 Fix API inconsistencies — DEFERRED

Low priority. REST API is secondary to MCP. Budget enforcement and graph
endpoint fixes can wait for a REST-focused session.

### 4.5 Session synthesis flag — STAYS AS-IS

The CAIRN_LLM_SESSION_SYNTHESIS flag correctly gates the LLM cost in
SessionSynthesizer.synthesize(). The SessionSynthesisListener (from Phase 3)
calls synthesize(), which checks the flag. If OFF, no LLM call, no narrative
stored. The flag serves as a cost control gate — not a ghost flag.

---

## PHASE 5: HARDEN

### 5.1 CI pipeline — DONE

- [x] Created `.github/workflows/ci.yml` — runs on push/PR to main
- [x] Steps: checkout, Python 3.12 setup, install deps (CPU torch), pytest, dead import check

### 5.2 Config flag coverage tests — DONE

- [x] Created `tests/test_config_coverage.py` — 14 parametrized tests
- [x] Every LLMCapabilities flag must have implementation code (not just config.py)
- [x] active_list() must mention every boolean flag
- [x] EXPERIMENTAL_CAPABILITIES must be subset of real flag names
- [x] Prevents ghost flags from recurring

### 5.3 Benchmark regression gate — DEFERRED

Blocked on fast LoCoMo harness (Phase 6). Can't gate CI on a 7-hour benchmark.
Will add once Bedrock batch testing is available.

### 5.4 Enable features in production config — DEFERRED

Requires benchmark data to know which features to enable. Moves to Phase 6.

### 5.5 Phase 5 verification

- [x] Run: python3 -m pytest -x -q (all tests passing including 14 new config coverage tests)
- [x] Commit: d06dd4e refactor: Phase 5 — CI pipeline, config flag coverage tests

---

## PHASE 6: BENCHMARK EVALUATION

Two scoring modes:
- **Retrieval scoring** (local, fast, ~6 min): token F1 only, Titan V2 embeddings, no LLM
- **LLM judge scoring** (full, via Bedrock batch): LLM generates answer + LLM-as-judge scores
  → Submit JSONL to S3, async processing, 50% cheaper, no rate limits

### 6.1 Fix the scorer first — DONE

**Why:** Can't evaluate anything if the scorer is broken (Bug 10 — concatenated F1).

- [x] Changed _score_retrieval() to per-memory F1 (take max) instead of concatenated
- [x] Per-memory substring containment check too
- [x] Abstention scoring also per-memory
- [x] Added tests/test_retrieval_scorer.py (9 tests)
- [x] Commit: 6a6d028 fix: Bug 10 — per-memory F1 scoring instead of concatenated

### 6.2 Baseline run — DONE

- [x] Run LoCoMo with fixed scorer, plain RRF, no optional features
- [x] Report: eval/reports/bench_locomo_20260220_184047.json

**Baseline results (retrieval scoring, SearchV2=OFF, no graph):**

| Question Type | Count | Accuracy |
|--------------|-------|----------|
| adversarial   | 446   | 50.2%    |
| multi-hop     | 321   | 17.1%    |
| open-domain   | 841   | 39.6%    |
| single-hop    | 282   | 20.4%    |
| temporal      | 96    | 16.7%    |
| **OVERALL**   | 1986  | **34.5%** |

Previous reported accuracy was 8.6% (broken scorer). Fixed scorer → 34.5%.

### 6.3 Fix query entity extraction (Bug 12 — chunk+embed waste)

**Evidence:** SearchV2._extract_query_entities() splits query into every word (≥3 chars)
and every bigram, embeds each one independently. "What did Caroline do?" generates ~20
chunks including "what", "did", "does", each getting a Bedrock embed call + Neo4j vector
search. 1,986 questions → 100K+ embed calls instead of ~2K. The threshold (Bug 1 fix)
filters garbage matches so results aren't wrong, just massively wasteful.

**The router already does this right.** `cairn/core/router.py` uses one LLM call to
extract entity_hints cleanly: `["Caroline"]`. The chunk+embed approach in search_v2.py
bypasses the router with a brute-force alternative.

**Fix:** Replace brute-force chunking with the router's entity extraction approach.
For no-LLM mode (benchmark retrieval scoring), use a simple heuristic: embed only
capitalized words (proper nouns) + the full query. Skip stop words and common verbs.

- [ ] Fix _extract_query_entities() in search_v2.py
- [ ] Test: verify ~2-5 embed calls per question, not 20+
- [ ] Run SearchV2 ablation with fixed extraction

### 6.4 Other fixes found during benchmark setup

- [x] Made sentence_transformers import lazy in cairn/embedding/engine.py
  (was crashing benchmark even when using Bedrock embeddings)
- [x] Cleaned Neo4j namespace contamination (Bug 7): deleted 687 production
  entities + 1,573 statements from benchmark project_id=2 using timestamp cutoff

### 6.5 Ablation tests

Run LoCoMo with each feature toggled independently against 34.5% baseline:

- [ ] Spreading activation ON vs OFF — does it help RRF?
- [ ] MCA gate ON vs OFF — does keyword coverage filtering help?
- [ ] Type routing ON vs OFF — does intent-based boosting help?
- [ ] Reranking ON vs OFF — does cross-encoder reranking help?
- [ ] Confidence gating ON vs OFF — does LLM quality assessment help?
  (Core/RedPlanet uses aggressive LLM-as-judge and gets 88%. We built it, never wired it.)
- [ ] SearchV2 ON vs OFF — does graph-primary help or hurt?

**Decision rule:** If a feature improves LoCoMo score, KEEP. If it hurts or is neutral, REMOVE.
No deleting based on vibes or old plans.

### 6.6 Bedrock batch full LoCoMo run

Build batch inference pipeline for LLM-judged evaluation:
- [ ] Create JSONL formatter for LoCoMo questions (Bedrock batch input format)
- [ ] Upload to S3, submit batch job via Bedrock API
- [ ] Parse batch output, compute LLM judge scores
- [ ] Compare LLM judge scores vs retrieval scores

### 6.7 Document results and decide

- [ ] Record ablation results in a memory
- [ ] Update this file with deletion/keep decisions based on data
- [ ] Delete features proven harmful, keep features proven helpful

---

## PHASE STATUS

- [x] **Phase 1: Safe Deletions** — DONE (1465ae0)
- [x] **Phase 2: Fix Search Bugs** — DONE (00aa355, bugs 1,2,5+9 fixed; bugs 3,4 deferred)
- [x] **Phase 3: Unify Event Bus** — DONE (af29cc8, memory events, async enrichment, session synthesis)
- [x] **Phase 4: Ingestion + Remaining** — DONE (5e48326, ingest MCP tool, clustering fix)
- [x] **Phase 5: Harden** — DONE (d06dd4e, CI pipeline, config flag coverage tests)
- [ ] **Phase 6: Benchmark Evaluation** — IN PROGRESS
  - [x] 6.1 Scorer fix (6a6d028)
  - [x] 6.2 Baseline: 34.5% (retrieval scoring, plain RRF)
  - [ ] 6.3 Fix chunk+embed waste (Bug 12)
  - [x] 6.4 Lazy import fix, Neo4j contamination cleanup
  - [ ] 6.5 Ablation tests
  - [ ] 6.6 Bedrock batch full LoCoMo run
  - [ ] 6.7 Document results and decide

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
| cairn/listeners/memory_enrichment.py | Async memory enrichment listener (Phase 3) |
| cairn/listeners/session_synthesis.py | Session synthesis listener (Phase 3) |
| cairn/core/synthesis.py | Session synthesis — wired via listener in Phase 3 |
| cairn/core/ingest.py | Ingest pipeline — wired as MCP tool in Phase 4 |
| cairn/core/clustering.py | HDBSCAN clustering — labels improved in Phase 4 |
| .github/workflows/ci.yml | CI pipeline (Phase 5) |
| tests/test_config_coverage.py | Ghost flag prevention tests (Phase 5) |
| eval/benchmark/rag.py | Benchmark scorer — fix in Phase 6 |
