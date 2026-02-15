# Roadmap

Current: **v0.38.x** — Model router, token observability, cost tracking.

---

## Next Up

### Prompt Engineering Audit
All prompts were modeled after a well-structured open-source MCP server during early development and haven't been systematically reviewed since. Full audit needed: token efficiency (are we wasting context window?), output format reliability (JSON parsing failures?), instruction clarity (does the LLM actually follow our rules?), few-shot example quality, and prompt-model fit (prompts tuned for one model may underperform on another). The extraction prompt was 325 lines before the v0.38.0 tightening — continued optimization possible.

### Benchmark Re-evaluation
The LoCoMo 81.7% was measured against v0.28. Cairn has evolved significantly since — graph-aware search signals, entity canonicalization, contradiction scoping, context budgets. Re-run the full eval suite against the current system to establish an updated baseline. The graph neighbor signal in RRF should help multi-hop queries. We need honest numbers.

### Agent Workspace Maturation
The workspace/messaging system (OpenCode integration, inter-agent messages, session dispatch) is functional but early. Next steps: better session lifecycle management, message-driven task chains, workspace health monitoring, and agent coordination patterns. This is the foundation for multi-agent workflows — it needs to get robust before we build on top of it.

### UI Interactive Editing
Turn the dashboard from read-only into a working interface. Edit memories inline, edit markdown content, update task status — all from the browser. (Task completion and terminal host editing shipped in v0.35.1.)

### Graph Entity Management
UI for Neo4j knowledge graph entities: visualize entity nodes, tag and merge duplicates, correct entity types, browse relationships. The dedup script (`cairn/scripts/dedup_entities.py`) handles bulk cleanup; the UI is for ongoing curation.

### Graph Search Handlers
Re-enable intent-routed graph search in search_v2. The graph neighbor signal is now in core RRF (v0.37.0); search_v2's dedicated graph handlers need quality validation and tuning. Target: improved multi-hop and relationship queries.

### Knowledge Graph Hardening
v0.37.0 laid the foundation — entity extraction, resolution, contradiction scoping, graph-aware search. Now make it trustworthy at scale. Entity resolution precision (are we merging the right things? missing obvious dupes?). Threshold tuning on the two-tier matcher. Canonicalization quality — does the known-entities hint actually reduce fragmentation, or does the LLM ignore it? Temporal lifecycle management — when should `invalid_at` propagate through related statements? Graph search weight tuning — the 35/20/15/15/10/5 split is a first guess. Measure, adjust, measure again.

### Test Infrastructure
201 unit tests, zero integration tests, zero UI tests. The unit tests mock everything — they validate logic in isolation but don't catch wiring bugs (wrong SQL, broken migrations, mismatched API contracts). Next steps: integration tests that stand up Postgres + Neo4j in containers and exercise real store→search→extract round-trips. API contract tests for the 55 REST endpoints. UI smoke tests (Playwright) for critical flows — search, capture, settings. CI should run the integration suite on every PR, not just lint and unit tests.

### Event-Digest Tension Detection
Compare session event digests against high-importance project memories. Flag memories where agent behavior consistently diverges from stored knowledge. Catches gradual drift that contradiction-on-store misses.

---

## Shipped

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
