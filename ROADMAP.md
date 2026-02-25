# Roadmap

Current: **v0.61.0** — 21-language code intelligence.

---

## Ongoing

**Benchmark re-evaluation.** LoCoMo 81.6% scored at v0.55 (full run, 1,986 questions across 5 categories). Re-run periodically as the system evolves. The graph neighbor signal, entity canonicalization, and contradiction scoping should affect scores.

**Knowledge graph hardening.** Entity resolution precision, canonicalization quality, threshold tuning, temporal lifecycle management, graph search weight tuning. Measure, adjust, measure again.

**Test infrastructure.** Integration tests with real Postgres + Neo4j containers. API contract tests for REST endpoints. UI smoke tests (Playwright). CI should run integration suite on PRs, not just lint and unit tests.

**Graph entity management UI.** Visualize entity nodes, merge duplicates, correct types, browse relationships from the dashboard.

**Plugin development guide.** Tutorial for adding custom embedding/LLM/reranker backends. The plugin registry pattern is a core extensibility feature — it needs documentation.

**Eval framework as CLI.** Let users run LoCoMo against their own config (`cairn eval --profile knowledge`). Answer "does switching to Ollama embeddings hurt my score?"

---

## Shipped

### v0.61.0 — "Polyglot" ✓

21-language code intelligence. From 2 languages to 21 in two sessions.

- [x] **12 new language parsers** — Swift, Scala, Kotlin, C#, Bash, SQL, HCL (Terraform), Dockerfile, JSON, YAML, TOML, Markdown. Each with language-specific symbol extraction tuned to idioms (Go receiver methods, Kotlin data classes, HCL resource blocks, Dockerfile build stages).
- [x] **Filename-based detection** — `Dockerfile` (no extension) recognised alongside `.dockerfile`. Registry supports both extension and filename matching.
- [x] **375 parser tests** — 205 new tests across 12 languages, all passing. Existing 170 tests unchanged.
- [x] **Previous session** — C, C++, Go, Java, PHP, Ruby, Rust parsers (7 languages, from v0.60.0 branch).

### v0.60.0 — "Drag Your Own Adventure" ✓

Drag-and-drop dashboard. Customizable widget grid.

- [x] **Drag-and-drop dashboard** — `react-grid-layout` v2, 11 widgets, edit mode, responsive breakpoints, localStorage persistence

### v0.59.x — "Chat Intelligence + UI Performance" ✓

Chat LLM tool surface expansion. UI responsiveness overhaul.

- [x] **Chat LLM: 10 → 17 tools** — added `modify_memory`, `discover_patterns`, `think`, `consolidate_memories`, `ingest_content`, `query_code`, `check_architecture`. The chat assistant can now edit memories, discover patterns, do structured reasoning, run code analysis, and ingest content — all conversationally.
- [x] **SQL query optimization** — LATERAL subqueries replace cartesian JOINs on projects and work items pages, window functions eliminate separate COUNT queries
- [x] **DB pool tuning** — min 2→4, max 10→15 for concurrent MCP + REST + background load
- [x] **Background clustering** — re-clustering runs in a thread instead of blocking requests
- [x] **t-SNE caching** — O(n²) computation cached with clustering staleness TTL
- [x] **Frontend API cache** — request deduplication, 30s stale-while-revalidate, mutation invalidation
- [x] **`useFetch` SWR mode** — cached data served instantly while revalidating in background
- [x] **Visibility-aware polling** — pauses when tab hidden, resumes on focus

### v0.59.0 — "Display IDs + REST API Parity" ✓

Jira-style work item IDs. Full REST coverage matching every MCP tool.

- [x] **Jira-style display IDs** — project-scoped sequential IDs (`ca-42`) replace hex-encoded `wi-XXXX` identifiers. Auto-generated prefixes with collision detection. Atomic `seq_num` allocation via `UPDATE...RETURNING`.
- [x] **`_resolve_id()` accepts both formats** — numeric IDs and display ID strings work everywhere (`work_item_id=42` or `work_item_id="ca-42"`)
- [x] **`PATCH /projects/{name}/prefix`** — customize project work item prefixes
- [x] **REST API parity** — full REST coverage for all MCP tool functionality. Extracted shared business logic from `server.py` into `cairn/core/orient.py` and `cairn/core/code_ops.py`. New endpoints for memory CRUD, code intelligence, dispatch, consolidate, orient, project links, and document updates.
- [x] **cairn-ui API client update** — TypeScript types and API client methods for all new endpoints, `short_id` → `display_id` across 9 component files
- [x] **`server.py` slimmed** — 600+ lines of inline business logic moved to dedicated core modules
- [x] Migration 032 (display IDs: `seq_num` on work_items, `work_item_prefix`/`work_item_next_seq` on projects, backfill, `short_id` column dropped)

### v0.58.x — "Code Intelligence" ✓

Per-project code understanding. Parse source files with tree-sitter, build a code graph in Neo4j, enforce architecture boundaries, search code by natural language, analyze cross-project dependencies — all through MCP.

- [x] **Architecture boundary rules** — YAML rule engine with `from`/`deny`/`allow` glob patterns, validated against Python imports via stdlib `ast`
- [x] **`code_index` MCP tool** — tree-sitter parsing with pluggable language modules (21 languages), content-hash incremental indexing, `CodeFile`/`CodeSymbol` nodes with `CONTAINS`/`IMPORTS` edges in Neo4j
- [x] **`.gitignore` support** — respects all `.gitignore` files in the tree (root + nested) via `pathspec` gitwildmatch. No hardcoded exclude lists.
- [x] **`code_query` MCP tool** — 11 actions: `dependents`, `dependencies`, `structure`, `impact`, `search`, `hotspots`, `entities`, `code_for_entity`, `cross_search`, `shared_deps`, `bridge`
- [x] **`code_describe` MCP tool** — LLM-generated natural language descriptions per symbol, embedded for semantic code search
- [x] **`arch_check` MCP tool** — boundary validation from YAML config or project docs, source-based or graph-backed evaluation, integration contracts
- [x] **TypeScript language module** — functions, classes, interfaces, enums, React components/hooks, ES6 imports, JSDoc extraction, TSX dialect support
- [x] **PageRank hotspot analysis** — identify structurally important files via NetworkX client-side PageRank
- [x] **Knowledge ↔ Code bridging** — `REFERENCED_IN` edges linking knowledge entities to code files/symbols, auto-wired after index and enrichment
- [x] **Cross-project analysis** — search symbols and find shared dependencies across all indexed projects
- [x] **Chunked Neo4j transactions** — batch upsert splits into 50-file chunks to stay within transaction memory limits
- [x] **Async MCP tools** — `insights`, `dispatch`, `consolidate`, `ingest`, `code_query`, `arch_check` use `asyncio.to_thread` to avoid blocking the event loop
- [x] **`architecture.yaml`** — 9 boundary rules for Cairn's own codebase (dogfood), 0 violations
- [x] **29 code intelligence tests** — parser, indexer, query, cross-project, arch rules, TypeScript

### v0.57.0 — "Frictionless Dispatch" ✓

Single-call agent dispatch, work items UI polish, breadcrumbs, expandable search, project detail overhaul.

- [x] **`dispatch()` MCP tool + REST endpoint** — single-call agent backgrounding
- [x] **Work items filter/sort split** — separate Filter and Sort controls
- [x] **Status/type SingleSelect** — honest single-value filters matching API semantics
- [x] **Assignee dropdown** — populated from fetched items' assignees
- [x] **Keyboard navigation on work items** — j/k to move, Enter to open
- [x] **Quick create project picker** — project dropdown when viewing all projects
- [x] **Breadcrumbs** — memory, doc, thinking, project detail pages
- [x] **Expandable search previews** — inline content expansion in dense mode
- [x] **Project detail overhaul** — memories first, scrollable sections, per-section filters, "View all" links
- [x] **LoCoMo benchmark: 81.6%** — up from 79.4%. Open-domain 86.2%, multi-hop 83.8%, adversarial 78.0%, temporal 74.5%, single-hop 73.4% (1,986 questions)
- [x] **Collaborative thinking sequences** — multi-agent contribution to shared threads

### v0.56.0 — "Use It or Lose It" ✓

Memory lifecycle. Access tracking, decay scoring, controlled forgetting, importance boosting, enrichment status tracking.

- [x] **Memory access tracking** — `access_count` and `last_accessed_at` columns, `MemoryAccessListener` on event bus
- [x] **Access-frequency search signal** — new RRF signal (~10% weight), gated behind `CAIRN_ACCESS_FREQUENCY`
- [x] **Enhanced decay scoring** — exponential decay combining age with access frequency
- [x] **Controlled forgetting** — `DecayWorker` background thread, auto-inactivation below threshold, protected classes, dry-run default
- [x] **Importance as RRF Signal 9** — ~8% weight, always active
- [x] **Enrichment status tracking** — `enrichment_status` column, migration 030, backfill from existing data
- [x] **`re_enrich()` method** — recovery path for failed/partial enrichments
- [x] **Zero-work enrichment detection** — warns on high-importance memories with no entities
- [x] **orient() merged trail** — PG+graph fusion, HA philosophy
- [x] **Enricher status returns** — `complete`/`partial`/`failed` instead of silent `{}`
- [x] Migrations 029 (memory lifecycle), 030 (enrichment status)

### v0.55.0 — "Show Your Work" ✓

LoCoMo benchmark, ingest tool, event-driven enrichment, CI pipeline.

- [x] **LoCoMo benchmark: 79.4%** — LLM-judged evaluation across 1,986 questions
- [x] **Ingest MCP tool** — `ingest()` accepts content or URL with chunking
- [x] **Memory events on event bus** — `memory.created`, `memory.updated`, `search.executed`
- [x] **Async memory enrichment** — `MemoryEnrichmentListener` via event bus with retry/backoff
- [x] **Session synthesis listener** — `SessionSynthesisListener` on `session_end`
- [x] **CI pipeline** — GitHub Actions: Python 3.12, pytest, dead import check
- [x] **Config flag coverage tests** — parametrized tests preventing ghost flags
- [x] **Query entity extraction fix** — proper noun extraction replacing brute-force word splitting
- [x] **Per-memory F1 scoring** — benchmark scorer fixed from concatenated to per-memory max

### v0.52.0 — "Event Horizon" ✓

Event-driven graph projection, startup reconciliation, dual-mode graph, deploy overhaul, UI polish.

- [x] **Event-driven graph projection** — replaced 15 inline dual-write touchpoints with event bus subscriber framework. `GraphProjectionListener` consumes events and syncs to Neo4j via idempotent MERGE.
- [x] **EventBus subscriber framework** — `subscribe(event_type, handler_name, fn)` with wildcard support. Dispatch records tracked in `event_dispatches` table with retry.
- [x] **EventDispatcher background worker** — polls pending dispatches, exponential backoff retry (5 attempts, 10s base).
- [x] **Startup reconciliation** — `reconcile_graph()` compares PG vs Neo4j state on boot. PG wins. Backfills `graph_uuid`.
- [x] **Dual-mode graph page** — auto-detects Neo4j availability, toggles between Entity (Neo4j) and Memory (Postgres) views. Graceful fallback.
- [x] **Graph mobile touch** — pinch-to-zoom, single-finger pan, tap-to-select, touch-drag repositioning.
- [x] **Task → work item promotion UI** — `POST /tasks/{id}/promote` endpoint + "Promote to Work Item" button in task sheet.
- [x] **Ops log enrichment** — expandable rows with error messages, session deep-links, full operation detail.
- [x] **Dashboard fixes** — work items widget (silent 422 from limit validation), entity chart selections persisted to localStorage.
- [x] **Deploy script rewrite** — local build + `docker save | scp | docker load`, no GHCR round-trip. `--skip-build` flag.
- [x] **DB connection hardening** — `@track_operation` unconditionally releases connections. Fixed `release_if_held()` leak.
- [x] **Chat fixes** — conversation auto-creation, streaming text accumulation, JSONB casting.
- [x] Migration 027 (event_dispatches), idempotent Neo4j methods, model router env config.

### v0.51.0 — "Connected Context" ✓

Session ↔ work item linking, event bus observability, cross-page navigation, UI component consolidation.

- [x] **Session ↔ Work Item linking** — `session_work_items` junction table (migration 026) with role escalation (touch → heartbeat → updated → created → claimed → completed). Auto-fires on create, update, claim, complete, heartbeat.
- [x] **Event bus observability** — `EventBusStats` with thread-safe counters, sliding-window health (healthy/degraded/unhealthy), surfaced in `/api/status`. 11 unit tests.
- [x] **Cross-page navigation** — project names, session names, cluster labels are now clickable links throughout the UI (memories, cairns, docs, sessions, memory sheet).
- [x] **`SingleSelect` component** — unified searchable select replacing all native `<select>` elements across 8 pages.
- [x] **Download support** — documents export as Markdown or PDF, memories export as Markdown with YAML frontmatter.
- [x] **Memory relations UI** — incoming/outgoing relations with color-coded types and direction arrows.
- [x] **Session/project detail enrichment** — sessions show memories + linked work items; projects show work items, memories, sessions.
- [x] **Work items view mode** — consolidated Completed dropdown + Ready toggle into single 5-mode View selector.
- [x] **Work item parent editing** — re-parent items via detail sheet.
- [x] **Session deep-linking** — `?selected=` query param on sessions page.
- [x] 3 new REST endpoints, `useLocalStorage` hook, `DownloadMenu` component.

### v0.50.0 — "Event Bus" ✓

Replaced the digest pipeline with a lightweight event bus. No LLM in the hot path.

- [x] **`EventBus` class** — publish, query, session lifecycle management. Individual events INSERTed with Postgres NOTIFY trigger for real-time SSE streaming.
- [x] **Migration 025** — `sessions` and `events` tables replacing JSONB batch approach. Postgres trigger function `notify_event()` for real-time streaming.
- [x] **Hook rewrite** — all core scripts POST individual events to `/api/events`. No JSONL files, no batching, no offset tracking. Fire-and-forget.
- [x] **Session auto-management** — server auto-creates sessions on `session_start` events, auto-closes on `session_end` events.
- [x] **Legacy digest pipeline removed** — `DigestWorker`, `DigestStats`, digest prompts, config, and tests deleted (~1,400 lines removed).
- [x] **Sessions page refactored** — uses event bus queries instead of digest-based session events.
- [x] **Work item session events** — events linked to work items shown in detail sheet.
- [x] **Hooks README rewritten** — full documentation of event bus architecture.
- [x] **Setup scripts updated** — event bus architecture and `CAIRN_URL` propagation.

### v0.49.0 — "Chat UI" ✓

assistant-ui integration. SSE streaming. Conversation persistence. Rich tool rendering. UI polish pass.

The chat becomes the front door for Cairn — create work, dispatch agents, review results, all from a conversation.

- [x] **assistant-ui integration** — Thread, Message, Composer primitives with markdown rendering, syntax highlighting
- [x] **SSE streaming** — `POST /chat/stream` with token-by-token streaming and tool call events
- [x] **Conversation persistence** — conversations + chat_messages tables, auto-title, CRUD endpoints
- [x] **Rich tool UIs** — 6 custom renderers: search, recall, store, status, list/create work items
- [x] **Project scoping** — per-conversation project context injected into system prompt
- [x] **Nav sidebar overhaul** — grouped sections (Core/Context/Reference/Deep Dive/Ops), attention badge on work items
- [x] **Dashboard operational strip** — work item status distribution, gated items, active sessions
- [x] **Memory type proportional bar** — OKLCH-colored distribution replacing flat type badges
- [x] **Empty states** — meaningful detail text with action hints across 6 pages
- [x] **README rewrite** — narrative reframed around the ideate-dispatch-review loop

### v0.48.0 — "Work Orchestration" ✓

Gate primitives, risk tiers, agent heartbeat, activity logging, cascading constraints, briefing action.

- [x] **Gate system** — human-in-the-loop checkpoints, timer gates, auto-gate on CRITICAL risk tier
- [x] **Risk tiers** — 4-level (patrol/caution/action/critical), inherited by children, UI badges
- [x] **Cascading constraints** — parent boundaries inherited + overridden by children
- [x] **Agent heartbeat** — working/stuck/done state reporting, stale detection
- [x] **Activity logging** — full audit trail in `work_item_activity` table with actor/timestamp/metadata
- [x] **Agent briefing** — assembled context with description, acceptance criteria, ancestor constraints, linked memories
- [x] **"Needs Your Input" UI** — gated items surfaced at top of work items page
- [x] **Inline quick create** — type title, press Enter. Press N to focus.
- [x] **Auto-refresh polling** — 10s interval with visibility-aware pausing and backoff
- [x] **Three-tier separation** — tasks (personal), work items (dispatchable), messages (deprecated)
- [x] **`promote` action** — tasks → work items with memory transfer
- [x] 6 new REST endpoints, 6 new MCP actions, Neo4j graph sync for gates/risk

### v0.47.0–v0.47.1 — "Work Management" ✓

Graph-native work items. Hierarchical decomposition. Agent-ready dispatch.

- [x] **WorkItem Neo4j nodes** — type, status, priority, hierarchical decomposition (replaced by Jira-style display IDs in v0.59.0)
- [x] **Graph edges** — PARENT_OF, BLOCKS, ASSIGNED_TO, RELATES_TO
- [x] **`ready` semantics** — Cypher: unblocked items as dispatch primitive
- [x] **Atomic claiming** — status + assignee in one operation
- [x] **MCP `work_items` tool** — 11 actions: create, list, update, claim, complete, add_child, block, unblock, ready, get, link_memories
- [x] **Work items UI** — tree-style list, status/type/project filtering, detail sheet, create dialog
- [x] **Embedding dimension reconciliation** — auto-fix 384→1024 mismatch on startup
- [x] Migration 022 (work_items), REST API, command palette integration

### v0.43.0 — "Operator Controls" ✓

Runtime-editable router, neo4j, and budget config. UI consistency pass.

- [x] **Model Router settings** — full-width card with enabled toggle + 3-tier config (capable/fast/chat), each with backend select, model, and daily budget
- [x] **Neo4j settings** — URI, user, password (secret-redacted), database fields editable from UI
- [x] **Token Budget settings** — 6 endpoint budgets (rules, search, recall, cairn_stack, insights, workspace) in 2-col grid
- [x] **Active Profile badge** — shows current CAIRN_PROFILE in System Overview when set
- [x] **Backend: router/neo4j/budget EDITABLE_KEYS** — 2-level nested config serialization for router tiers, neo4j added to section classes and env map
- [x] **Command palette completeness** — added 9 missing pages (chat, messages, sessions, cairns, docs, graph, workspace, terminal, analytics) to match sidebar nav
- [x] **Sessions error handling** — error state in list, error banner with retry in detail view, PageLayout wrapper
- [x] **Capture page** — adopted PageLayout, removed manual h1
- [x] **Projects page** — adopted PageLayout, added empty state with icon

### v0.42.0 — "Settings Pane Hardening" ✓

Configuration surface legibility overhaul. Stable vs experimental distinction, tooltips, dirty tracking.

- [x] **Shadcn Tooltip component** — Radix-based, wrapped in TooltipProvider at layout root
- [x] **Experimental badge variant** — amber-themed CVA variant for unproven capabilities
- [x] **Capability metadata** — all 14 capabilities (including missing `cairn_narratives`) with label + description
- [x] **Stable/Experimental split** — capabilities card split into two sections with amber border divider, using API `experimental` array for classification
- [x] **Tooltip descriptions** — `(i)` icons on all capabilities and key settings (enrichment, reranker candidates, chunk size/overlap, analytics costs)
- [x] **Dirty field indicators** — per-row `bg-primary/5` tint and dot when field has unsaved changes
- [x] **Settings layout overhaul** — card reordering (overview → embedding → LLM → reranker → auth → terminal → analytics → ingestion → capabilities → database → types), 2-col grid, full-width capabilities card
- [x] **SettingsResponse type fix** — `experimental`, `profiles`, `active_profile` fields wired from API

### v0.41.0 — "Session Intelligence" ✓

Event pipeline redesign. Batch digests are now intermediate working state — only session-level synthesis produces durable knowledge. Multi-agent ready.

- [x] **Pipeline redesign: CAPTURE → BATCH → DIGEST → SYNTHESIZE → EXTRACT** — DigestWorker no longer creates per-batch memories. Session close synthesizes all batch digests into one structured session narrative via LLM.
- [x] **Significance filter** — synthesis classifies sessions as low/medium/high. Low = DB record only (no memory, no graph noise). Medium/High = one memory with extraction.
- [x] **Structured synthesis output** — JSON with significance, summary, decisions[], outcomes[], discoveries[], dead_ends[], open_threads[]. Knowledge extractor gets rich input instead of 2-sentence batch summaries.
- [x] **Multi-agent schema** — `agent_id`, `agent_type` (interactive/background/ci/autonomous), `parent_session` columns on session_events. Ingest API and hooks pass agent metadata. Ready for spawned agent tracking.
- [x] **Session lifecycle fix** — `is_active` uses explicit `closed_at` column instead of 2-hour heuristic. Sessions marked closed with synthesis result stored as JSONB.
- [x] **Sessions → formalized episodic nodes** — sessions now have structured metadata, lifecycle tracking, and synthesis records (from v0.41.0 Graph Deepening roadmap item).
- [x] Migration 020 (agent metadata + session lifecycle)

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
