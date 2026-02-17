# Roadmap

Current: **v0.50.0** — TBD.

---

## Next Up

### Ongoing

**Benchmark re-evaluation.** LoCoMo 81.7% was measured at v0.28. Re-run against current system. The graph neighbor signal, entity canonicalization, and contradiction scoping should affect scores. Publish updated numbers.

**Knowledge graph hardening.** Entity resolution precision, canonicalization quality, threshold tuning, temporal lifecycle management, graph search weight tuning. Measure, adjust, measure again.

**Test infrastructure.** Integration tests with real Postgres + Neo4j containers. API contract tests for REST endpoints. UI smoke tests (Playwright). CI should run integration suite on PRs, not just lint and unit tests.

**Graph entity management UI.** Visualize entity nodes, merge duplicates, correct types, browse relationships from the dashboard.

**Plugin development guide.** Tutorial for adding custom embedding/LLM/reranker backends. The plugin registry pattern is a core extensibility feature — it needs documentation.

**Eval framework as CLI.** Let users run LoCoMo against their own config (`cairn eval --profile knowledge`). Answer "does switching to Ollama embeddings hurt my score?"

---

## Shipped

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

- [x] **WorkItem Neo4j nodes** — type, status, priority, Beads-style hierarchical IDs (wi-a3f8, .1, .1.1)
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
