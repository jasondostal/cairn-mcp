# Roadmap

Current: **v0.34.0** — Editable settings with DB persistence.

---

## Next Up

### UI Interactive Editing
Turn the dashboard from read-only into a working interface. Edit memories inline, complete/update tasks, edit markdown content, update task status — all from the browser.

### Graph Entity Management
UI for Neo4j knowledge graph entities: visualize entity nodes, tag and merge duplicates, correct entity types, browse relationships. Depends on graph extraction being populated.

### Graph Search Handlers
Re-enable intent-routed graph search in search_v2. Backfill graph extraction for remaining conversations, tune merge strategy, validate quality. Target: improved multi-hop and relationship queries.

### Event-Digest Tension Detection
During cairn synthesis, compare session event digests against high-importance project memories. Flag memories where agent behavior consistently diverges from stored knowledge. Catches gradual drift that contradiction-on-store misses.

---

## Shipped

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
