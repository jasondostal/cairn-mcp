# Roadmap

Current: **v0.40.x** — Tiered profiles, unified search, contributor DX.

---

## Next Up

### v0.41.0 — Graph Deepening

Implement the "Everything is a Node" decision from v0.37.0 beyond memories and entities.

- [ ] Thinking sequences → graph entity nodes with THOUGHT edges
- [ ] Tasks → graph entity nodes with ASSIGNED_TO, BLOCKS, LINKED_TO edges
- [ ] Sessions → formalized episodic nodes
- [ ] Cross-project entity bridges — shared entities surface inter-project connections
- [ ] One query model for everything knowledge-related

### v0.42.0 — Graph-Augmented Search

Move search from signal fusion toward retrieval strategy selection based on query shape. SearchV2 is already the sole entry point (v0.40.0); this release adds meaningful strategy dispatch.

- [ ] Intent router selects retrieval strategy: vector (vague queries), graph traversal (entity-anchored), aspect-filtered (structured queries like "X's preferences")
- [ ] Re-enable and validate graph search handlers (entity_lookup, aspect_query, relationship, temporal)
- [ ] Vector similarity remains primary fallback for queries with no entity anchors

### v0.43.0 — Single-Pass Boot

Replace the multi-call boot sequence with a unified orientation tool.

- [ ] `orient(project)` — one MCP tool returning rules, recent trail, open tasks, relevant learnings
- [ ] Individual tools (rules, trail, search, tasks) remain available for granular use
- [ ] Graph-backed: one traversal assembles full session context


### Ongoing

**Benchmark re-evaluation.** LoCoMo 81.7% was measured at v0.28. Re-run against current system. The graph neighbor signal, entity canonicalization, and contradiction scoping should affect scores. Publish updated numbers.

**Knowledge graph hardening.** Entity resolution precision, canonicalization quality, threshold tuning, temporal lifecycle management, graph search weight tuning. Measure, adjust, measure again.

**Test infrastructure.** Integration tests with real Postgres + Neo4j containers. API contract tests for REST endpoints. UI smoke tests (Playwright). CI should run integration suite on PRs, not just lint and unit tests.

**UI interactive editing.** Edit memories inline, update markdown content, manage task status from the browser.

**Graph entity management UI.** Visualize entity nodes, merge duplicates, correct types, browse relationships from the dashboard.

**Plugin development guide.** Tutorial for adding custom embedding/LLM/reranker backends. The plugin registry pattern is a core extensibility feature — it needs documentation.

**Eval framework as CLI.** Let users run LoCoMo against their own config (`cairn eval --profile knowledge`). Answer "does switching to Ollama embeddings hurt my score?"

---

## Shipped

### v0.40.0 — "Tiered Profiles + Contributor DX" ✓

Configuration profiles, unified search, and codebase split for maintainability.

- [x] **`CAIRN_PROFILE` env var** — 4 named profiles (`vector`, `enriched`, `knowledge`, `enterprise`) set capability flags and feature toggles per deployment tier. Individual env vars always override profile defaults.
- [x] **Unified search pipeline** — `SearchV2` is now the sole search entry point. Passthrough mode (zero overhead) when `search_v2` capability is off; enhanced pipeline (intent routing + reranking + token budgets) when on. Graceful degradation: enhanced → RRF → vector → empty.
- [x] **`api.py` split into route modules** — 1641-line monolith replaced by `cairn/api/` package with 16 focused modules using `register_routes(router, svc)` pattern. Largest module: 261 lines.
- [x] **Experimental feature labels** — `EXPERIMENTAL_CAPABILITIES` set marks 6 capabilities (query_expansion, confidence_gating, type_routing, spreading_activation, mca_gate, cairn_narratives). Status and settings API responses include experimental labels.
- [x] **Bug fix: session close NameError** — `digest_worker` variable was never extracted from `svc` in the session close endpoint (latent since v0.39.0).

### v0.39.0 — "Event Pipeline Repair" ✓

Digest output now feeds the knowledge graph. Session activity enters the graph automatically.

- [x] **`session-end.sh` rewritten** — removed dead `/api/cairns` POST, now calls `POST /api/sessions/{name}/close`
- [x] **DigestWorker → MemoryStore wiring** — digests stored as `progress` memories, triggering extraction → graph → trail
- [x] **`POST /sessions/{name}/close` endpoint** — synchronous session teardown with immediate digestion
- [x] **`session-start.sh` simplified** — removed dead `/api/cairns?limit=5` fetch
- [x] **Full pipeline validated** — hook capture → event ingest → digest → memory store → extraction → graph → trail

### v0.38.0 — "Token Observatory" ✓

Model router and token cost tracking. Never burn 80M tokens in a day again.

- [x] **Model router** — `ModelRouter` routes LLM calls by task complexity: `capable` (extraction), `fast` (enrichment, digest, clustering), `chat` (user-facing). Per-tier daily token budgets with automatic fallback. `OperationLLM` wrapper means zero changes to callers.
- [x] **Actual token counts** — all 4 LLM backends extract real token counts from API responses instead of `len(text)//4` estimation
- [x] **Token budget analytics** — `GET /api/analytics/token-budget` with per-model daily usage, estimated USD cost, and configurable rates
- [x] **Extraction prompt tightened** — 325 → 137 lines (41% reduction, saves ~1,100 input tokens per store)
- [x] **Query expansion default OFF** — eliminates 3-5 unnecessary LLM calls per session boot

### v0.37.0 — "Everything is a Node" ✓

Graph-centric architecture pivot. Cairns retired in favor of knowledge graph trail.

- [x] **`trail()` replaces `cairns()`** — boot orientation via Neo4j entity activity, not pre-computed summaries
- [x] **Migration 019** — drops `cairns` table and `cairn_id` FK
- [x] **Graph-aware RRF signal** — memories sharing entities with top candidates get relevance boost
- [x] **Entity canonicalization** — extraction LLM receives known entity hints, reducing duplicates
- [x] **Two-tier entity resolution** — type-scoped (0.85) with type-agnostic fallback (0.95)
- [x] **Dangling object resolution** — post-extraction pass links string objects to entities
- [x] **Contradiction aspect scoping** — only Identity/Preference/Belief/Directive contradict; events accumulate
- [x] **Temporal graph queries** — `recent_activity()`, `session_context()`, `temporal_entities()`
- [x] **Entity merge** — `merge_entities()` on graph provider + `dedup_entities.py` script
- [x] **Export/import scripts** — curated memory migration tooling with timestamp preservation

### v0.36.x — Agent Workspace + Budgets ✓

- [x] **Agent Workspace** — Cairn as orchestration layer above OpenCode sessions
- [x] **Context budget system** — cap MCP tool response sizes
- [x] **Gitignore hardening** — prevent accidental commits of dev artifacts

### v0.35.1 — QoL Batch + Docs ✓

Dashboard layout, density, and polish.

- [x] **Dashboard layout rearranged** — Memory Growth + Tokens (2-col), Heatmap (full), Health, Ops + Cost (2-col), Model + Project tables, Type badges. Removed redundant Projects grid.
- [x] **Task completion from UI** — `POST /tasks/{id}/complete` endpoint + Mark Complete button
- [x] **Terminal host editing** — edit dialog with pre-fill, pencil icon on hover
- [x] **Chat persistence** — sessionStorage (capped 100), rAF scroll fix, New Chat button
- [x] **Ops log density** — dense rows, project/session links, model column
- [x] **Token chart readability** — unstacked series, differentiated fill opacity
- [x] **Sidebar scroll fix** — `overflow-y-auto` on desktop nav
- [x] **Chat LLM prompt tightened** — send_message restricted to async-only
- [x] **Analytics labels** — `(none)` → `System`, `(no project)` → `Unassigned`
- [x] **README overhaul** — new intro, accurate counts (15 tools, 55 endpoints, 24 pages, 17 migrations), synced embedded compose, added missing config vars
- [x] **All docs accuracy pass** — ROADMAP, CHANGELOG, cairn-ui/README, hooks README, pyproject.toml

### v0.35.0 — Voice-Aware Extraction + Hook Auth ✓

- [x] **Voice-aware knowledge extraction** — speaker tag for extraction quality
- [x] **Hook auth support** — API key header in example hooks

### v0.34.2 — MCP Auth Fix ✓

- [x] **Remove MCP endpoint auth** — Claude Code OAuth discovery incompatibility

### v0.34.0 — Editable Settings ✓

Runtime config from the UI, persisted in DB.

- [x] **DB-persisted settings** — `app_settings` table, resolution order: default → env → DB override
- [x] **42 editable keys** — LLM, reranker, capabilities, analytics, auth, terminal, ingestion
- [x] **Settings page rewrite** — text/number/toggle/select inputs, source badges, per-field reset, restart banner
- [x] **Secret redaction** — API redacts `db.password`, API keys, encryption keys server-side
- [x] **Deferred service creation** — base config at import, DB overrides applied after connect
- [x] Migration 017 (app_settings), 3 new API endpoints

### v0.33.0 — Web Terminal + Messages ✓

Browser-based SSH. Agent-to-agent messaging.

- [x] **Dual-backend web terminal** — native (xterm.js + WebSocket + asyncssh) or ttyd (iframe). Host management with encrypted credentials. Feature-flagged via `CAIRN_TERMINAL_BACKEND`.
- [x] **Inter-agent messages** — `messages` MCP tool, Messages UI page, chat tool integration. Send, inbox, mark read, archive, priority.
- [x] Migration 015 (messages), Migration 016 (ssh_hosts)
- [x] 12 new REST endpoints + 1 WebSocket endpoint

### v0.31.0 — Live Session Dashboard ✓

Watch Claude Code sessions in real-time.

- [x] **Live session dashboard** — `/sessions` page with active/recent sessions, event counts, digest status
- [x] Click into a session to see every tool call with input, response, timestamp
- [x] Active sessions pulse green, auto-refresh

### v0.30.0 — Agentic Chat ✓

The Chat page LLM can search memories, browse projects, and store knowledge.

- [x] **7 chat tools** — search_memories, recall_memory, store_memory, list_projects, system_status, get_rules, list_tasks
- [x] Tool calls shown as expandable blocks in the UI
- [x] Graceful degradation for models without tool support

### v0.29.0 — Chat Page ✓

Direct LLM conversation in the browser.

- [x] **Chat UI** — bubble-style messages, keyboard submit, multi-line, model name display
- [x] `POST /api/chat` endpoint with OpenAI-style messages

### v0.28.0 — LoCoMo Benchmark + Knowledge Graph ✓

81.7% on the standard conversational memory benchmark.

- [x] **LoCoMo 81.7%** — validated against Maharana et al. (ACL 2024). All 5 categories.
- [x] **Neo4j knowledge graph** — entity/statement/triple storage, BFS traversal, contradiction detection
- [x] **Combined knowledge extraction** — single LLM call extracts entities, statements, triples, tags, importance
- [x] **Intent-routed search (search_v2)** — 5 intent types with typed handlers
- [x] **Cross-encoder reranking** — Bedrock-powered, +5.5 points on benchmark
- [x] **Speaker attribution** — `author` field on memories
- [x] **Reranker pluggable architecture** — local cross-encoder and Bedrock backends

### v0.27.0 — Analytics Dashboard ✓

Chart-heavy home page with full observability.

- [x] **Analytics instrumentation** — all backends emit usage events with model name, tokens, latency
- [x] **8 analytics endpoints** — overview, timeseries, operations, projects, models, memory-growth, sparklines, heatmap
- [x] **Dashboard redesign** — sparkline KPIs, operations/token charts, activity heatmap, model table

### v0.26.0 — Behavioral Tool Descriptions ✓

- [x] All 14 MCP tool docstrings rewritten with TRIGGER keywords, WHEN TO USE guidance, cross-tool references

### v0.25.0 — Layout Overhaul ✓

- [x] **PageLayout + EmptyState** components, 15 pages migrated to fixed-header layout

### v0.24.0 — Multi-Select Filters ✓

- [x] **Multi-select filters** across all 9 list pages with typeahead, badges, comma-separated API params

### v0.23.0 — Temporal Decay + Drift Detection ✓

- [x] **Recency as 4th RRF signal** — newer memories rank higher
- [x] **`drift_check` MCP tool** — file content hash comparison for stale memories
- [x] **OpenAI-compatible embedding backend**
- [x] **Digest pipeline observability**

### v0.22.0 — Multi-IDE + Security ✓

- [x] **Multi-IDE hook adapters** — Cursor, Windsurf, Cline, Continue
- [x] **SSRF protection** on URL ingestion
- [x] **MCP endpoint auth enforcement**

### v0.21.0 — Model Observability ✓

- [x] Per-model health, invocation counts, token usage, error tracking for all backends

### v0.20.0 — Bedrock Embeddings ✓

- [x] **Bedrock Titan V2 embeddings** — 8,192 token context, configurable dimensions
- [x] **Auto-reconciliation** — startup detects dimension mismatch and resizes automatically

### v0.19.0 — HDBSCAN Clustering ✓

- [x] **HDBSCAN replaces DBSCAN** — auto-tuned density thresholds, meaningful clusters

### v0.18.0 — Open Architecture ✓

- [x] **Pluggable LLM providers** — Ollama, Bedrock, Gemini, OpenAI-compatible
- [x] **Pluggable embedding providers** — local SentenceTransformer, extensible
- [x] **Optional API key auth** — configurable header, auth proxy compatible
- [x] Keyboard navigation, activity heatmap, dense views, toast notifications

### v0.17.0 and earlier ✓

See [CHANGELOG.md](CHANGELOG.md) for the full history back to v0.1.0.
