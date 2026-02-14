# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.35.0] - 2026-02-14

### Added
- **Voice-aware knowledge extraction** — extraction LLM now receives a `[Speaker: user|assistant|collaborative]`
  tag when the memory has an `author` field set. Improves extraction filtering: user-authored
  memories are extracted with full confidence, assistant-authored memories filter speculative
  suggestions, collaborative memories extract shared decisions. Gracefully ignored when author
  is null (no behavioral change for existing deployments).
- **Hook auth support** — example hooks (`session-start.sh`, `session-end.sh`, `log-event.sh`)
  now pass `CAIRN_API_KEY` as an `X-API-Key` header when the env var is set. Required for
  deployments with `CAIRN_AUTH_ENABLED=true`.
- `migrate_v2.py` passes `author` to extraction during bulk re-extraction runs.

## [0.34.2] - 2026-02-14

### Fixed
- **Remove MCP endpoint auth** — `/mcp` no longer requires API key authentication.
  Claude Code's HTTP transport forces OAuth discovery before connecting, which fails
  with 404 on servers that use static API keys. This made MCP unreachable from Claude
  Code. `/api` routes remain auth-gated when `CAIRN_AUTH_ENABLED=true`.

## [0.34.0] - 2026-02-14

### Added
- **Editable settings with DB persistence** — settings are now editable through the web UI
  and persisted in a PostgreSQL `app_settings` table. Resolution order: dataclass default
  → env var → DB override (highest priority wins). All changes require container restart
  to take effect (~5s).
  - **42 editable keys** — LLM backend/model/keys/URLs, reranker config, all 13 capability
    flags, analytics settings, auth config, terminal config, enrichment toggle, ingest
    chunk settings.
  - **Read-only fields** — embedding (would invalidate all vectors), database, transport/port.
  - **Source tracking** — per-field source badge (`default`/`env`/`db`) shows where each
    value comes from.
  - **Restart detection** — "Restart required" banner appears when DB overrides differ from
    running config.
  - **Reset** — per-field reset button removes DB override, reverting to env/default.
- `GET /api/settings` — expanded response with `values`, `sources`, `editable` keys list,
  and `pending_restart` flag. Secrets redacted server-side.
- `PATCH /api/settings` — bulk update editable settings with enum/range/type validation.
- `DELETE /api/settings/{key}` — remove single DB override.
- Migration 017 — `app_settings` key-value table.
- `cairn/storage/settings_store.py` — load, upsert, and delete setting overrides.
- `config.py` additions: `EDITABLE_KEYS` whitelist, `apply_overrides()` for frozen
  dataclass rebuilding, `config_to_flat()` serializer, `env_values()` snapshot.
- Deferred service creation — module-level loads base config only; DB overrides applied
  during lifespan after database connects. `create_services()` accepts optional `db` param.

### Changed
- Settings page fully rewritten — from read-only display to editable form with text inputs,
  number inputs, switch toggles, select dropdowns, section-level save, and toast feedback.
- Server lifecycle refactored — `_start_workers()` and `_stop_workers()` helpers eliminate
  duplication between stdio and HTTP modes.
- API version bumped to 0.34.0.

### Security
- `GET /api/settings` redacts secrets (`db.password`, API keys, encryption keys) server-side.
  Previously returned all values in plaintext.

## [0.33.0] - 2026-02-13

### Added
- **Web terminal** — dual-backend SSH terminal at `/terminal`. Two modes controlled via
  `CAIRN_TERMINAL_BACKEND` env var (default: `disabled`):
  - **Native mode** — xterm.js in the browser, WebSocket to cairn backend, asyncssh proxy
    to target hosts. Fernet-encrypted credential storage. Full PTY with resize support.
  - **ttyd mode** — embed an external [ttyd](https://github.com/tsl0922/ttyd) container
    via iframe. Zero WebSocket complexity, battle-tested.
  - Host management UI: add/edit/delete hosts, adapts form fields based on active backend.
  - `TerminalHostManager` service with CRUD operations and credential encryption.
  - `TerminalConfig` dataclass — 4 env vars for backend selection, encryption key, session
    limits, connect timeout.
- **Messages** — inter-agent communication layer. Agents (and humans) can leave notes for
  each other, check inboxes, and manage message state.
  - `messages` MCP tool (#15) — send, inbox, mark_read, mark_all_read, archive, unread_count.
  - `messages` chat tool — the agentic chat LLM can check and send messages.
  - Messages UI page at `/messages` with project filtering, priority indicators, batch
    mark-as-read, and archive support.
- 6 new REST endpoints for messages: `GET /api/messages/unread-count`,
  `GET/POST /api/messages`, `PATCH /api/messages/{id}`, `POST /api/messages/mark-all-read`.
- 6 new REST endpoints for terminal host management: `GET /api/terminal/config`,
  `GET/POST /api/terminal/hosts`, `GET/PATCH/DELETE /api/terminal/hosts/{id}`.
- WebSocket endpoint: `/api/terminal/ws/{host_id}` — bidirectional terminal proxy
  (native mode only). Text → terminal input, JSON resize messages → PTY resize.
- Migration 015 — `messages` table with indexes for unread and project queries.
- Migration 016 — `ssh_hosts` table for terminal host management (both modes).
- Terminal and Messages nav items in sidebar.

### Dependencies
- `asyncssh>=2.14` added as optional terminal dependency (`pip install cairn-mcp[terminal]`).
  Included in the Docker image for native terminal mode.
- `@xterm/xterm` and `@xterm/addon-fit` added to frontend dependencies.

## [0.31.0] - 2026-02-13

### Added
- **Live session dashboard** — `/sessions` page shows active and recent Claude Code sessions
  with event counts, digest status, and cairn linkage. Click into a session to see the full
  event stream: every tool call with name, input preview, expandable response, and timestamp.
- Active sessions show a pulsing green dot and auto-refresh every 5 seconds.
- Session list auto-refreshes every 30 seconds.
- `GET /api/sessions` — lists recent sessions grouped by session_name with stats (event count,
  batch count, digest progress, active status, cairn status).
- `GET /api/sessions/{session_name}/events` — returns flattened event stream + digests for a session.
- Reinstalled Claude Code hooks (SessionStart, PostToolUse, SessionEnd).

## [0.30.0] - 2026-02-13

### Added
- **Agentic chat** — the Chat page LLM can now call Cairn tools. Ask it to search memories,
  browse projects, check system status, store new memories, list tasks, or view rules. The LLM
  uses Bedrock Converse API's native tool calling in an agent loop (max 10 iterations).
- 7 chat tools exposed: `search_memories`, `recall_memory`, `store_memory`, `list_projects`,
  `system_status`, `get_rules`, `list_tasks`.
- Tool calls shown in the UI as expandable `<details>` blocks — wrench icon with tool name,
  click to see output. Clean, non-intrusive.
- `LLMInterface.generate_with_tools()` — new method with default text-only fallback.
  `BedrockLLM` overrides with full Converse API tool calling support.
- Graceful degradation: if the model doesn't support tool use (ValidationException), automatically
  falls back to plain text chat for the session.
- `cairn/chat_tools.py` — tool definitions and `ChatToolExecutor` that maps tool calls to
  Cairn service operations.

## [0.29.0] - 2026-02-13

### Added
- **Chat page** — direct conversational interface to the embedded LLM at `/chat`. Bubble-style
  UI with message history, keyboard submit (Enter), multi-line support (Shift+Enter), model
  name display, and loading state. Messages are ephemeral (not stored). Uses the same LLM
  backend configured for Cairn (Kimi K2.5 via Bedrock, Ollama, etc.).
- `POST /api/chat` — accepts OpenAI-style `messages` array, returns LLM response + model name.
- Chat nav item in sidebar (MessageCircle icon).

## [0.28.2] - 2026-02-13

### Added
- **Speaker attribution** — new `author` field on memories tracks who created each memory.
  Use `"user"` for human-authored, `"assistant"` for AI-authored, or a specific name. Both
  voices are valid — this is for attribution, not filtering. Shared memory, shared ownership.
- `store()` and `modify()` MCP tools accept optional `author` parameter.
- Author returned in `recall()`, `search()`, timeline, and REST API responses.
- Migration 014 adds `author VARCHAR(100)` to memories table (nullable for backward compat).

## [0.28.1] - 2026-02-13

### Changed
- **Reranker refactored to pluggable provider architecture** — reranker now follows the same
  pattern as embedding and LLM backends: `RerankerConfig` dataclass, `RerankerInterface` ABC,
  per-backend modules in `cairn/core/reranker/` package, factory with plugin registry. Supports
  `local` (cross-encoder) and `bedrock` (Amazon Rerank API) backends. Custom providers via
  `register_reranker_provider(name, factory_fn)`.
- `RerankerConfig` added to `Config` — replaces scattered `reranker_model` and `rerank_candidates`
  fields. Hydrated from `CAIRN_RERANKER_BACKEND`, `CAIRN_RERANKER_MODEL`, `CAIRN_RERANK_CANDIDATES`,
  `CAIRN_RERANKER_BEDROCK_MODEL`, `CAIRN_RERANKER_REGION` env vars.
- `Services` uses `get_reranker(config.reranker)` factory instead of direct `Reranker()` instantiation.
- Bedrock reranker backend now properly wired through config system (was previously only usable
  in eval scripts with manual construction).

### Removed
- `cairn/core/reranker.py` — monolithic file replaced by `cairn/core/reranker/` package
  (`__init__.py`, `interface.py`, `local.py`, `bedrock.py`).

## [0.28.0] - 2026-02-13

### Added
- **81.7% on LoCoMo benchmark** — validated against the standard evaluation for conversational
  memory systems (Maharana et al., ACL 2024). Competitive with Mem0 (68.5%), Zep (75.1%),
  and Letta (74.0%). All 5 question categories included (some published systems skip adversarial).
- **Kimi K2.5 support** — Moonshot AI's trillion-parameter MoE model via AWS Bedrock.
  $0.60/M input tokens. Used for answer generation and LLM-as-judge scoring in benchmarks.
- **7-step Chain-of-Thought answer generation** — structured reasoning pipeline for RAG:
  memory extraction, key details, cross-memory linking, time calculation, contradiction check,
  detail verification, final answer. Adapted from competitive analysis of top-scoring systems.
- **Timestamp-aware context formatting** — memory timestamps extracted and reformatted for
  prominence in RAG context, improving temporal reasoning accuracy.
- **Neo4j knowledge graph** — entity/statement/triple storage with vector + fulltext indexes,
  entity resolution via embedding similarity, contradiction detection with temporal invalidation,
  BFS traversal for multi-hop reasoning. Project-scoped. Graceful degradation when Neo4j unavailable.
- **Combined knowledge extraction** — single LLM call at ingestion extracts entities (9 types),
  statements (11 aspects), triples, tags, importance, and summary. Pydantic-validated structured
  output with retry. Replaces separate enrichment when enabled.
- **Intent-routed search (search_v2)** — LLM query router classifies intent into 5 types
  (aspect_query, entity_lookup, temporal, exploratory, relationship) with typed handlers
  dispatching to Neo4j graph or PostgreSQL as appropriate. Falls back to RRF on failure.
- **Cross-encoder reranking** — Bedrock-powered reranker scores candidates after retrieval.
  Proven +5.5 points on benchmark.
- **LoCoMo benchmark framework** — full evaluation pipeline: dataset loader, two-pass ingestion
  (normalize + extract), RAG answer generation, LLM-as-judge scoring, per-category breakdown,
  parallel execution, JSON reports. Supports model comparison and strategy comparison.
- **Two-pass ingestion strategy** — conversation normalization followed by structured fact
  extraction for benchmark evaluation.
- **Pipeline analysis tooling** — per-question failure analysis across 4 gates
  (IN_DB, RRF_TOP50, RERANK_TOP10, RAG_CORRECT).

### Changed
- **Search quality section in README** — now includes validated LoCoMo benchmark score with
  per-category breakdown, methodology details, and competitive comparison table.

## [0.27.2] - 2026-02-12

### Fixed
- **Search page crash** — `related_files` can be `null` for memories without file
  associations. Added optional chaining (`?.length`) in search results, memory sheet,
  and memory detail page to prevent `TypeError` when rendering.

## [0.27.1] - 2026-02-12

### Fixed
- **DB connection release crash** — `release_if_held()` referenced non-existent
  `psycopg.pq.TransactionStatus.INTRANSACTION` enum member; corrected to `INTRANS`.
  This caused `AttributeError` on every request, crashing the server under load.
  Closes [#2](https://github.com/jasondostal/cairn-mcp/issues/2).
- **Ollama thinking token leakage** — added `"think": False` to Ollama `generate()`
  payload to prevent thinking-capable models (Qwen3, DeepSeek R1) from emitting
  chain-of-thought tokens into structured responses. Non-thinking models safely
  ignore this parameter. (PR [#1](https://github.com/jasondostal/cairn-mcp/pull/1)
  by [@manabe-daiki](https://github.com/manabe-daiki))

## [0.27.0] - 2026-02-11

### Added
- **Analytics instrumentation** — all embedding and LLM backends now emit `UsageEvent`
  rows with model name, token counts, and latency. New `emit_usage_event()` helper in
  `cairn/core/stats.py` with deferred import to avoid circular deps. 7 backends instrumented
  (3 embedding: engine, Bedrock, OpenAI-compat; 4 LLM: Bedrock, Ollama, OpenAI-compat, Gemini).
- **8 analytics REST endpoints** — `GET /analytics/overview`, `/timeseries`, `/operations`,
  `/projects`, `/models`, `/memory-growth`, `/sparklines`, `/heatmap`. Powered by
  `AnalyticsQueryEngine` with pre-aggregated rollups from `metric_rollups` table.
- **Chart-heavy dashboard** — full rewrite of the home page with: sparkline KPI strip
  (memories, cairns, projects, clusters with 7-day deltas), operations volume bar chart,
  stacked token usage area chart, memory type growth stacked area chart, activity heatmap,
  compact health strip for embedding/LLM/digest, model performance table, project breakdown
  table, cost projection, and memory type badges. Time range selector (7d/30d/90d).
- **Migration 010** — `usage_events`, `metric_rollups`, `rollup_state` tables with indexes
  for analytics queries.
- **Migration 011** — performance indexes for dashboard queries (`memories` by created_at/type,
  `cairns` by set_at, `usage_events` by model/timestamp).
- **Dynamic version display** — sidebar footer fetches version from `/api/status` instead
  of hardcoded constant. Status endpoint now includes `version` field from `cairn.__version__`.

### Fixed
- **OKLCH chart colors** — all recharts components were wrapping CSS custom properties in
  `hsl()` (e.g. `hsl(var(--chart-1))`), but the theme defines colors as raw OKLCH values.
  `hsl(oklch(...))` is invalid CSS, causing all chart series to render as the same fallback
  color. Fixed across 5 component files.
- **DB password alignment** — Python config defaults (`cairn/config.py`, `eval/corpus_export.py`)
  now match docker-compose default (`cairn-dev-password`) instead of the legacy `cairn` value.

### Changed
- Analytics tracker initialized before embedding/LLM backends in `services.py` so the
  singleton is available when backends start emitting events.
- API version bumped to 0.27.0.
- `cairn-ui` package version bumped to 0.27.0.

## [0.26.0] - 2026-02-11

### Changed
- **Behavioral tool descriptions** — all 14 MCP tool docstrings rewritten with
  TRIGGER keywords, WHEN TO USE guidance, PATTERN/WORKFLOW sections, and cross-tool
  references. Tool descriptions now coach agent behavior rather than just documenting
  API surface. Inspired by analysis of MiniMe/Recallium and cortex-mcp-kit patterns.
- **Server instructions enriched** — top-level MCP instructions now include the
  "search before guessing" principle, session startup sequence, mid-task search
  reminder, progressive disclosure pattern, and storage philosophy.
- **`search` tool** — now lists 15+ natural language trigger phrases (e.g., "how do
  we", "where is", "what's the command for") and explicitly states: search BEFORE
  guessing, SSH-ing, or asking the user.
- **`store` tool** — WHEN TO STORE / DON'T STORE guidance with consolidation
  philosophy ("one comprehensive memory > multiple fragments").
- **`cairns` tool** — session start/end workflow with boot sequence connection.
- **`rules` tool** — CRITICAL flag for session start loading.
- API version bumped to 0.26.0.

## [0.25.0] - 2026-02-11

### Added
- **`PageLayout` component** — reusable flex column layout with fixed header
  (title, optional title extras, optional filters) and independently scrollable
  content area. Eliminates `position: sticky` issues within the main scroll
  container. (`cairn-ui/src/components/page-layout.tsx`)
- **`EmptyState` component** — centered icon + message + optional detail text
  for empty list/search states. Replaces bare `<p>` tags across all pages.
  (`cairn-ui/src/components/empty-state.tsx`)
- **Favicon** — `cairn-mark-trail.svg` wired as the browser tab icon via
  Next.js metadata in `layout.tsx`.
- **Back buttons on all detail pages** — thinking sequence detail and project
  detail pages now have explicit back navigation.

### Changed
- **15 pages migrated to `PageLayout`** — all list pages (timeline, search,
  thinking, cairns, tasks, rules, docs, clusters, cluster visualization,
  knowledge graph) and all detail pages (cairn detail, thinking detail, doc
  detail, memory detail, project detail) now use the consistent fixed-header
  layout. Filters and title controls stay pinned while content scrolls.
- **Deterministic back navigation** — all detail pages use `<Link>` to their
  parent list page instead of `router.back()`. Predictable, bookmarkable,
  no browser history dependency.
- **Styled empty states** — 7 list pages and 2 detail pages upgraded from
  plain text to the `EmptyState` component with icon and contextual messaging.
- API version bumped to 0.25.0.

## [0.24.0] - 2026-02-11

### Added
- **Multi-select filters across all UI pages** — every project/type filter dropdown
  is now a multi-select with typeahead search, badge pills, "+N more" overflow,
  individual remove, clear all, and select all. Filter by multiple projects or types
  simultaneously. 9 pages migrated (search, timeline, tasks, thinking, cairns, docs,
  rules, clusters, cluster visualization).
- **New `MultiSelect` component** (`cairn-ui/src/components/ui/multi-select.tsx`) —
  reusable multi-select built on shadcn Command + Popover + Badge primitives.
- **Comma-separated multi-value API params** — all filter endpoints (`/timeline`,
  `/search`, `/tasks`, `/thinking`, `/cairns`, `/rules`, `/docs`) accept
  comma-separated `project` and `type` params (e.g. `?project=cairn,llm-context`).
  Backend uses PostgreSQL `ANY()` for efficient multi-value matching.

### Removed
- **`FilterCombobox` component** — replaced entirely by `MultiSelect`. No migration
  needed for API consumers — single values still work as before.

### Changed
- API version bumped to 0.24.0.
- `api.ts` `get()` helper accepts `string | string[]` params, auto-joining arrays.

## [0.23.1] - 2026-02-11

### Fixed
- **Connection pool exhaustion** — read-only API endpoints (status, search, graph,
  timeline, drift) never released DB connections after completing, leaving them
  checked out with stale transactions. Under concurrent load this exhausted the
  pool (max 10) causing `PoolTimeout` after 30s. Added `release_if_held()` and a
  FastAPI dependency that returns connections after every request.

## [0.23.0] - 2026-02-11

### Added
- **Temporal decay in search** — recency is now the fourth signal in RRF hybrid
  search. Newer memories rank higher without suppressing highly relevant older
  ones. Uses `updated_at` for freshness.
- **Code-aware drift detection** — new `drift_check` MCP tool compares file content
  hashes stored at memory creation against current hashes. Returns memories with
  stale file references. New `file_hashes` JSONB column (migration 009).
- **OpenAI-compatible embedding backend** — works with any `/v1/embeddings` API
  (OpenAI, Ollama, vLLM, LM Studio, Together). No SDK dependency.
- **Digest pipeline observability** — batches processed/failed, events digested,
  queue depth, avg latency, health state. Exposed via `/api/status`.
- **Knowledge graph enhancements** — cluster membership, temporal age, and
  server-computed sizing on graph nodes. UI adds cluster coloring mode
  and temporal opacity toggle.

### Changed
- RRF weights rebalanced: vector/keyword/tag (0.60/0.25/0.15) →
  vector/recency/keyword/tag (0.50/0.20/0.20/0.10).
- `store` accepts optional `file_hashes` parameter.
- Embedding factory recognizes `"openai"` as built-in backend.
- API version bumped to 0.23.0.

## [0.22.1] - 2026-02-11

### Security
- **SSRF protection on URL ingestion** — `ingest(url=...)` now validates URLs before fetching: blocks non-HTTP schemes, known metadata endpoints (169.254.169.254, metadata.google.internal), loopback addresses, and resolves DNS to reject private/reserved IPs. Prevents server-side request forgery via the ingest pipeline.
- **MCP endpoint auth enforcement** — when `CAIRN_AUTH_ENABLED=true`, the `/mcp` endpoint now requires the same API key as `/api`. Previously, MCP was unprotected even with auth enabled, allowing unauthenticated access to all tools.

## [0.22.0] - 2026-02-11

### Added
- **Multi-IDE hook adapters** — `examples/hooks/adapters/` with thin wrappers for Cursor (3 scripts), Windsurf (1 script with auto session-init), and Cline (3 scripts with JSON response wrapping). Each adapter translates IDE-specific field names to Cairn's core contract using `jq` defensive fallbacks. Claude Code continues to call core scripts directly.
- **Multi-IDE setup script** — `scripts/setup.sh` detects installed IDEs (Claude Code, Cursor, Windsurf, Cline, Continue), configures MCP connections via JSON merge, and optionally installs hook adapters. Supports `--dry-run`. Existing `scripts/setup-hooks.sh` preserved for backward compatibility.
- **MCP Registry** — `server.json` manifest and verification label for MCP Registry submission.

### Changed
- **README restructured for multi-IDE** — "Connect your agent" → "Connect your IDE" with generic-first MCP config, IDE config location table, setup script reference, and stdio in a collapsible. IDE badges added (Claude Code, Cursor, Windsurf, Cline, Continue). Tier 3 description and hooks section updated to list all supported IDEs. IDE hook capability matrix added.
- **Hooks README rewritten for multi-IDE** — per-IDE setup in collapsible sections, adapter architecture diagram, core script contract table, capability matrix, and honest caveat about field name validation across IDE versions.

### Fixed
- **Orphaned memory reconciliation** — memories stored via MCP without `session_name` are now claimed at cairn-set time by matching project + timestamp window from `session_events`. Agents no longer need to pass `session_name` on every `store()` call — the system self-heals when setting the cairn.

## [0.21.0] - 2026-02-10

### Added
- **Model observability** — per-model health, invocation counts, estimated token usage, and error tracking for all embedding and LLM backends. In-memory stats (resets on restart) via thread-safe `ModelStats` class.
- **Status endpoint redesign** — `status` tool and `GET /api/status` now return a `models` object with `embedding` and `llm` sub-objects, each containing: backend name, model ID, health state (healthy/degraded/unhealthy/unknown), call count, estimated tokens, error count, last call/error timestamps, and last error message.
- Health derivation: 3+ consecutive failures = unhealthy, any error in rolling window of 5 = degraded, all success = healthy.
- All 6 backends instrumented: Bedrock embedding, local SentenceTransformer, Bedrock LLM, Ollama, Gemini, OpenAI-compatible.

### Changed
- Status response replaces flat `embedding_model`, `embedding_dimensions`, `llm_backend`, `llm_model` fields with structured `models` object. Consumers should migrate to `models.embedding` and `models.llm`.

## [0.20.1] - 2026-02-10

### Added
- **Project field on modify** — `modify(action="update", project="new-project")` moves a memory to a different project. Enables project consolidation without direct SQL.
- **Bulk operations script** — `scripts/bulk_ops.py` with three commands:
  - `demote-progress` — batch-lower importance of all progress-type memories (default target: 0.3)
  - `move-project --from X --to Y` — move all memories + docs + tasks + thinking sequences + events + cairns between projects
  - `cleanup-projects` — inventory all projects with active/inactive counts, flag empty ones
  - All commands support `--dry-run` for preview.

## [0.20.0] - 2026-02-10

### Added
- **Bedrock Titan Text Embeddings V2 backend** — new built-in embedding provider (`CAIRN_EMBEDDING_BACKEND=bedrock`) using Amazon Titan Text Embeddings V2 via Bedrock. 8,192 token context (vs 256 for local MiniLM), configurable output dimensions (256/512/1024). Same retry pattern as the Bedrock LLM backend. ~$0.02/1M tokens — effectively free at typical scales.
- **Config-driven vector dimensions with auto-reconciliation** — on startup, Cairn compares the configured `CAIRN_EMBEDDING_DIMENSIONS` against the actual database schema. If they differ, it automatically resizes the `vector(N)` columns, nulls out stale embeddings, clears clusters, and recreates the HNSW index. Handles fresh installs, backend switches, and dimension changes without manual migration.
- **Re-embedding script** — `scripts/reembed.py` backfills memories with NULL embeddings after a backend switch. Progress logging every 50 memories, cost estimate for Bedrock.
- New env vars: `CAIRN_EMBEDDING_BEDROCK_MODEL` (default: `amazon.titan-embed-text-v2:0`), `CAIRN_EMBEDDING_BEDROCK_REGION` (falls back to `AWS_DEFAULT_REGION`).
- 9 new tests for Bedrock embedding (request body, retry logic, factory routing, interface contract).

### Changed
- `EmbeddingConfig` expanded with `bedrock_model` and `bedrock_region` fields.
- Embedding factory recognizes `"bedrock"` as a built-in backend alongside `"local"`.
- Both server lifespan paths (stdio + HTTP) call `reconcile_vector_dimensions()` after migrations.

## [0.19.0] - 2026-02-10

### Changed
- **HDBSCAN replaces DBSCAN for clustering** — DBSCAN with eps=0.65 collapsed 560 memories into a single mega-cluster. HDBSCAN auto-tunes density thresholds, producing meaningful topic clusters (11 clusters on 561 memories in testing). No new dependencies — uses `sklearn.cluster.HDBSCAN` (scikit-learn >= 1.3). Default params: `min_cluster_size=5`, `min_samples=3`, `metric="cosine"`.
- **Confidence scores from HDBSCAN probabilities** — cluster confidence is now derived from HDBSCAN's per-point membership probabilities (mean of member probabilities) instead of the arbitrary `1 - avg_distance/eps` formula. More principled, better range.
- **No precomputed distance matrix** — HDBSCAN works directly on embeddings with cosine metric, eliminating the O(n²) distance matrix construction step.

## [0.18.1] - 2026-02-10

### Fixed
- **Cairn stack cross-project** — MCP tool now allows omitting `project` on `cairns(action="stack")` to view cairns across all projects. Core method already supported this; the MCP handler was incorrectly rejecting it.

## [0.18.0] - 2026-02-10

### Added
- **Pluggable LLM providers** — LLM backend is now a factory with a provider registry. Built-in: Ollama, Bedrock, Gemini, and OpenAI-compatible (covers OpenAI, Groq, Together, Mistral, LM Studio, vLLM, and anything that speaks the OpenAI chat format). Custom providers can be registered via `register_llm_provider(name, factory_fn)`. Zero SDK dependencies for Gemini and OpenAI — pure `urllib` with built-in retry logic.
- **Pluggable embedding providers** — embedding engine abstracted behind `EmbeddingInterface` with the same factory/registry pattern. Built-in: `local` (SentenceTransformer, unchanged). Custom providers via `register_embedding_provider(name, factory_fn)`.
- **Optional API key auth** — lightweight middleware on all `/api` routes. Off by default. When enabled, checks `X-API-Key` header (header name configurable for auth proxy compatibility). Health, swagger, and OpenAPI endpoints exempt. MCP endpoint unaffected. Compatible with Authentik, Caddy, nginx, or any reverse proxy that injects auth headers.
- **Memory relations in API responses** — `GET /api/memories/:id` and search results now include a `relations` array showing incoming/outgoing relationships (extends, contradicts, implements, depends_on, related) with direction, summary, and linked memory type.
- **Search score transparency** — search results include `score_components` object breaking down the vector, keyword, and tag contributions to the final RRF score.
- **Thinking tree visualization** — `/thinking/:id` redesigned as a hierarchical tree with collapsible branches, color-coded thought types, and a tree/list view toggle.
- **Keyboard navigation** — `j`/`k` (vim-style) and arrow keys navigate lists on Search and Timeline pages. Enter to open, Esc to clear. New `useKeyboardNav()` hook.
- **Activity heatmap** — 52-day GitHub-style contribution heatmap on the Timeline page. Shows memory creation patterns at a glance.
- **Dense/compact views** — toggle between card and dense row layouts on Docs, Tasks, and Timeline pages. Consistent toggle across all list surfaces.
- **Toast notifications** — Sonner-based toasts for background operations (capture success/error, etc.).
- **Sidebar version + clock** — footer shows app version and live time.
- **Capture page: inline entity extraction** — `@mentions` auto-select projects, `#hashtags` auto-add tags, URLs auto-fill the URL field.
- **Memory relations panel** — memory detail sheet shows clickable incoming/outgoing relations with color-coded relation types.
- **Search score breakdown** — hover tooltip on search results shows vector/keyword/tag percentage contribution with color-coded bars.
- **Next.js auth middleware** — `cairn-ui/middleware.ts` injects `CAIRN_API_KEY` into proxied `/api/*` requests server-side, so the browser never sees the key.
- 2 new test files: `test_embedding_factory.py` (7 tests), `test_llm_factory.py` (8 tests + optional live smoke tests for Gemini and OpenAI).

### Changed
- `LLMConfig` expanded with Gemini and OpenAI settings.
- `EmbeddingConfig` expanded with `backend` field (default: `local`).
- `Config` gains `AuthConfig` section (enabled, api_key, header_name).
- `Services` uses factory functions (`get_llm`, `get_embedding_engine`) instead of direct instantiation.
- Knowledge graph node sizing adjusted for better visual weight (`5 + importance * 8`).
- `docker-compose.yml` adds auth env vars to cairn service and `CAIRN_API_KEY` to cairn-ui service.
- API version bumped to 0.18.0.
- `cairn-ui` package version bumped to 0.18.0.

### Dependencies
- Added `sonner@^2.0.0` (frontend toast notifications).

## [0.17.0] - 2026-02-10

### Added
- **Capture UI** — new `/capture` page in the web UI. Auto-focused textarea, project selector, tag input, memory type selector, and URL field. Keyboard-first: Ctrl+Enter to submit, slash commands for inline project/type switching (type `/decision` or `/cairn` in the textarea). Remembers last-used project.
- **Slash commands** — type `/` in the capture textarea to set memory type (`/decision`, `/rule`, `/learning`, etc.) or switch project (`/cairn`, `/llm-context`). Arrow keys navigate, Enter selects, Esc dismisses. The slash text is removed from content on selection.
- **URL extraction** — `POST /api/ingest` now accepts an optional `url` field. If URL provided without content, fetches the page and extracts readable text via `trafilatura`. If both URL and content, attaches URL as source metadata. Title auto-extracted from page metadata.
- **Browser bookmarklet** — `GET /api/bookmarklet.js` serves a one-click bookmarklet. Grabs page URL, document title, and selected text, opens the capture UI with fields pre-filled. Install instructions on the capture page.
- **iOS Shortcut support** — the ingest API accepts `source: "ios-shortcut"` for tracking. Setup instructions on the capture page.
- **`memory_type` on ingest** — `POST /api/ingest` now accepts `memory_type` parameter, threaded through to stored memories. Previously hardcoded to "note".
- "New Capture" added to Cmd+K command palette.
- Updated branding: "Persistent memory for agents and humans."

### Changed
- Capture page is second in nav (after Dashboard).
- `/api/ingest` validation relaxed: `content` OR `url` required (previously `content` was mandatory).

### Dependencies
- Added `trafilatura>=2.0` for URL content extraction.

## [0.16.0] - 2026-02-09

### Added
- **Smart ingestion pipeline** — unified `POST /api/ingest` endpoint that classifies, chunks, deduplicates, and routes content in a single call. Replaces manual decisions about whether content is a doc, a memory, or both.
- **Chonkie chunking** — large documents are split into searchable memories using markdown-aware chunking (`RecursiveChunker` with markdown recipe). Preserves heading structure and code blocks at chunk boundaries.
- **LLM content classification** — auto-determines whether content should be stored as a doc (reference material), memory (working knowledge), or both. Explicit `hint` parameter for override. Graceful fallback to "memory" when LLM unavailable.
- **Ingestion dedup** — content-hash based deduplication via `ingestion_log` table. Second ingest of identical content returns `{"status": "duplicate"}` with reference to the original.
- **Chunk→doc linkage** — `source_doc_id` column on `memories` table links chunks back to their parent document for traceability.
- **Migration 008** — `ingestion_log` table (source, content_hash, target_type, target_ids, chunk_count) with unique index on content_hash. `source_doc_id` FK column on memories.
- **Configurable chunking** — `CAIRN_INGEST_CHUNK_SIZE` (default 512 tokens) and `CAIRN_INGEST_CHUNK_OVERLAP` (default 64 tokens) env vars. Content under 2000 chars stored as single memory without chunking.

### Changed
- `MemoryStore.store()` accepts optional `source_doc_id` parameter for chunk→doc linkage.
- `MemoryStore.store()` accepts `enrich=False` to skip LLM enrichment and relationship extraction while still generating embeddings. Used by the ingest pipeline for chunk storage — follows RAG best practice of enriching at the document level, not per-chunk.
- `Services` dataclass expanded with `ingest_pipeline` field.
- API version bumped to 0.16.0.
- `cairn-ui` package version bumped to 0.16.0.

### Dependencies
- Added `chonkie` for markdown-aware text chunking.

## [0.15.0] - 2026-02-10

### Added
- **Content ingestion endpoints** — three new REST write endpoints for ingesting content without going through MCP:
  - `POST /api/ingest/doc` — create a single project document
  - `POST /api/ingest/docs` — batch create multiple project documents
  - `POST /api/ingest/memory` — store a memory via REST (full embedding + enrichment pipeline)
- Batch endpoint supports partial success — returns per-item errors alongside successful creates.
- All endpoints validate `doc_type` and `memory_type` against allowed values, auto-create projects.

### Changed
- API description updated from "read-only" to reflect write capability.
- API version bumped to 0.15.0.

## [0.14.0] - 2026-02-10

### Added
- **Docs browser** — new `/docs` list page and `/docs/:id` reading view in the web UI. Browse, filter, and read project documents with full rendered markdown (GFM tables, task lists, strikethrough) without leaving Cairn.
- **Expanded doc types** — `VALID_DOC_TYPES` extended from `[brief, prd, plan]` to include `primer`, `writeup`, and `guide`. Covers real usage beyond planning docs.
- **Cross-project doc listing** — `ProjectManager.list_all_docs()` returns docs across all projects with optional project/type filters and pagination. Powers the new REST endpoint and UI.
- **Single doc fetch** — `ProjectManager.get_doc(doc_id)` retrieves a document by ID with project name joined.
- **Document titles** — Migration 007 adds `title` column to `project_documents`. MCP `projects` tool and `create_doc`/`update_doc` accept optional `title` parameter. UI falls back to first `# heading` from content when title is NULL.
- **REST endpoints** — `GET /api/docs` (list with project/type/limit/offset filters) and `GET /api/docs/:id` (single doc with full content).
- **`DocTypeBadge` component** — color-coded badge for doc types (blue/purple/amber/green/teal/orange). Follows `MemoryTypeBadge` pattern.
- **Docs nav entry** — FileText icon between Projects and Clusters in the sidebar.
- `react-markdown` + `remark-gfm` dependencies for markdown rendering in the detail view.
- `@tailwindcss/typography` for `prose` classes on the reading view.

### Changed
- FastAPI Swagger UI moved from `/docs` to `/swagger` to avoid collision with the new docs endpoint.
- API version bumped to 0.14.0.
- `cairn-ui` package version bumped to 0.14.0.

## [0.13.0] - 2026-02-09

### Added
- **Contradiction escalation on store** — when relationship extraction detects a `contradicts` relation against a high-importance memory (>= 0.7), the store response includes a `conflicts` list with the contradicted memory's summary, importance, and a suggested action. Piggybacks on existing `relationship_extract` capability — no new flag needed.
- **Contradiction-aware search ranking** — memories with incoming `contradicts` relations get their search score multiplied by 0.5 (configurable via `CONTRADICTION_PENALTY`). Applied consistently across all three search modes (hybrid, keyword, vector). A contradicted memory needs to be 2x more relevant to outrank its replacement.
- **Thinking conclusion dupe rule** — global behavioral rule (#567) prevents storing thinking sequence conclusions as separate memories, which was creating duplicates found during consolidation.
- 7 new tests (94 total across 16 suites): 4 for contradiction escalation, 3 for contradiction-aware search

### Design
- Memories aren't stale because they're old — they're stale because something newer says they're wrong. The `contradicts` relation already existed in `memory_relations` (v0.6.0); v0.13.0 makes it actionable: loud at store time (conflicts list), quiet at search time (score penalty).
- No new database migration, no new LLM capability flag, no new env vars. Pure logic on existing infrastructure.

## [0.12.0] - 2026-02-09

### Added
- **Event Pipeline v2 (CAPTURE → SHIP → DIGEST → CRYSTALLIZE)** — events are now captured with full fidelity, shipped incrementally in batches of 25, digested by LLM into rolling summaries, and crystallized into cairn narratives. Long sessions no longer break narrative synthesis.
- **`POST /api/events/ingest`** (202 Accepted) — streaming event ingestion endpoint. Idempotent upsert on `(project, session_name, batch_number)`. Validates batch size (max 200 events).
- **`GET /api/events`** — list event batches with digest status for debugging and UI consumption.
- **DigestWorker** — background daemon thread polls for undigested event batches, processes them through LLM one at a time, backs off on error (3x poll interval, capped at 60s). Graceful degradation: LLM failure leaves batch undigested, retries on next cycle.
- **Migration 006** — `session_events` table with UNIQUE constraint on `(project_id, session_name, batch_number)` for idempotent re-shipping. Partial index on `digest IS NULL` for efficient polling.
- **`CAIRN_LLM_EVENT_DIGEST`** env var — toggleable event batch digestion (default: `true`)
- **Digest-aware cairn narratives** — `CairnManager.set()` queries `session_events` for pre-digested summaries. When digests exist, uses a dedicated prompt that works with structured summaries instead of raw events. Falls back to raw events (Pipeline v1) when no digests are available.
- 17 new tests: 15 for DigestWorker (capability matrix, batch processing, lifecycle, immediate digestion) + 2 for digest-aware cairn synthesis

### Changed
- **Hook scripts rewritten for Pipeline v2:**
  - `session-start.sh` — initializes `.offset` sidecar file alongside event log
  - `log-event.sh` — rewritten as a dumb pipe: captures full `tool_input` (JSON) and `tool_response` (capped at 2000 chars), ships batches of 25 via background `curl POST /api/events/ingest`, `.offset` sidecar tracks shipped vs unshipped
  - `session-end.sh` — ships remaining unshipped events as final batch, POSTs to `/api/cairns` without events payload (server pulls digests from `session_events`), falls back to Pipeline v1 when `/api/events/ingest` returns 404
- `Services` dataclass expanded with `digest_worker` field
- Server lifespans (stdio + HTTP) now start/stop DigestWorker alongside migrations

### Backward Compatibility
- **Old hooks + new server:** session-end.sh ships raw events via POST /api/cairns → CairnManager finds no digests → falls back to raw events prompt. Zero breakage.
- **New hooks + old server:** POST /api/events/ingest returns 404, curl fails silently. Cairn set works from stones only. Degraded but functional.

## [0.11.0] - 2026-02-09

### Fixed
- **Race condition in cairn set** — the agent (via MCP) and session-end hook (via REST POST) could both try to set a cairn for the same session. The first one succeeded; the second got a 409 error and its events were lost. `CairnManager.set()` now uses upsert semantics: whichever path arrives second merges its data (events, narrative re-synthesis) into the existing cairn. No more empty cairns.
- **Events deleted on POST** — `session-end.sh` deleted the event log after POSTing, even on failure. Events are now archived to `~/.cairn/events/archive/` instead of deleted.

### Added
- **Server-side event archive** — `CAIRN_EVENT_ARCHIVE_DIR` env var enables writing raw JSONL events to a file-based archive on cairn set. Docker Compose mounts a `cairn-events` volume at `/data/events` by default.
- **Setup script** — `scripts/setup-hooks.sh` interactively checks dependencies, tests Cairn connectivity, creates event directories, and generates a ready-to-paste Claude Code settings.json snippet. Includes optional pipeline test.
- **Hooks documentation overhaul** — `examples/hooks/README.md` rewritten with Quick Start guides for both Claude Code and other MCP clients, environment variable table, verification steps, troubleshooting section, and updated architecture diagram showing the upsert flow.

### Changed
- **AWS credentials via environment variables** — `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_DEFAULT_REGION` are now passed as env vars in docker-compose instead of mounting `~/.aws` as a volume. Simpler, consistent with how all other config is handled. Just add them to your `.env` file.
- `POST /api/cairns` no longer returns 409 on duplicate session — returns the existing/merged cairn instead
- `CairnManager.set()` returns `status: "already_exists"` or `status: "merged"` when updating an existing cairn
- Docker Compose adds `cairn-events` named volume mounted at `/data/events` on the cairn service

## [0.10.0] - 2026-02-08

### Added
- **Knowledge graph visualization** — interactive d3-force graph at `/graph`. Nodes are memories (colored by type, sized by importance), edges are relationships (colored by relation type). Zoom, pan, drag nodes, hover tooltips, click to open memory sheet. Filter by project and relation type (extends, contradicts, implements, depends_on, related).
- **Graph REST endpoint** — `GET /api/graph?project=&relation_type=` returns nodes, edges, and stats for the relationship graph.

### Improved
- **Cluster list page** — better card layout with expandable sample memories, confidence badges
- **Cluster visualization** — improved scatter plot controls, better hover states and legend

## [0.9.0] - 2026-02-08

### Added
- **Connection pooling** — `psycopg_pool.ConnectionPool` replaces single shared connection, with thread-local tracking and auto-recovery from failed transactions. Fixes potential race condition under concurrent REST API requests.
- **Configurable CORS origins** — `CAIRN_CORS_ORIGINS` env var (comma-separated). Defaults to `*` for backwards compatibility; set to specific origins when behind a reverse proxy.
- **Persistent event logs** — hook scripts now write to `~/.cairn/events/` (configurable via `CAIRN_EVENT_DIR`) instead of `/tmp`
- **Search quality documentation** — new "Search Quality" section in README with eval methodology, limitations, and honest assessment of the benchmark

### Changed
- **Default LLM backend** — switched from `bedrock` to `ollama` across config, docker-compose, and .env.example. Ollama is free, local, and runs on commodity hardware. Bedrock still fully supported.
- RRF module docstring documents k=60 origin (Cormack et al. 2009), weight rationale, and known limitations
- Eval claim in README qualified: "83.8% recall@10 on our internal benchmark (50-memory synthetic corpus, 25 hand-labeled queries)"
- Confidence gating description clarified as advisory (returns a confidence score but does not filter results)

### Fixed
- Hook scripts default port corrected from 8002 to 8000

### Dependencies
- Added `psycopg_pool>=3.1` to project dependencies

## [0.8.0] - 2026-02-08

### Added
- **Cairns UI page** — new list page (`/cairns`) and detail page (`/cairns/:id`) for browsing the session trail. List shows title, session name, narrative preview, stone count, and compressed status. Detail page renders full narrative, linked stones (click to open memory sheet), and collapsible event timeline.
- **"All projects" filter** — Cairns, Tasks, and Thinking list pages now support viewing across all projects. "All" button deselects the project filter; cards show a project badge when viewing all. Backend endpoints (`GET /api/cairns`, `GET /api/tasks`, `GET /api/thinking`) now accept optional `project` parameter.
- **`get_project()` read-only lookup** — new utility function returns project ID or `None` without creating phantom projects. All read paths (cairns stack, tasks list, thinking list, project docs/links) switched from `get_or_create_project` to `get_project`.
- **Migration 005 — partial indexes** — two partial indexes on `memories` filtered by `is_active = true`: one for timeline queries (`project_id, created_at DESC`), one for session grouping (`project_id, session_name`).

### Changed
- `CairnManager.stack()` now accepts optional `project` (returns all projects when `None`), includes project name in response
- `TaskManager.list_tasks()` now accepts optional `project`, includes project name in response
- `ThinkingEngine.list_sequences()` now accepts optional `project`, includes project name in response
- `cairn-ui` package version bumped to 0.8.0
- Cairns nav item added to sidebar (Landmark icon, between Timeline and Search)

### Fixed
- **Empty cairn noise** — `CairnManager.set()` now returns `{"skipped": true}` when session has no stones and no events, preventing noise cairns from accumulating
- **Phantom project creation on read paths** — reading docs, links, tasks, thinking sequences, or cairns for a nonexistent project no longer silently creates an empty project row
- Removed unused `get_or_create_project` import from `synthesis.py`

## [0.7.1] - 2026-02-08

### Added
- **Session name alignment** — `session-start.sh` now computes and outputs the session_name to agent context (e.g., `"Session name for this session: 2026-02-08-8045a3"`), and writes it into the event log's first entry. `session-end.sh` reads session_name from the event log instead of recomputing, eliminating midnight-drift mismatches. Organic memory rule (#507) updated to reference hook-provided session_name.
- **Mote-aware narrative synthesis** — cairn narratives now synthesize from both stored memories (stones) AND the mote event stream (tool calls captured by hooks). New `CAIRN_MOTE_NARRATIVE_SYSTEM_PROMPT` produces richer narratives that weave the timeline of what happened with the agent's deliberate observations. Sessions with zero organic memories but rich tool activity now get meaningful narratives instead of empty cairns.
- 2 new tests for mote-aware narrative synthesis (events-only synthesis, combined stones+events prompt selection)

### Changed
- `build_cairn_narrative_messages()` now accepts optional `events` parameter; when present, switches to mote-aware prompt and appends a summarized event timeline (capped at 50 events)
- `CairnManager.set()` now triggers LLM synthesis when events are present, even if no stones match the session
- README restructured — three-tier knowledge capture is now the lead section instead of a buried bullet point

### Fixed
- **Empty cairn bug** — cairns created by hooks were empty because `session-end.sh` recomputed session_name (could differ from what `session-start.sh` told the agent). Now both hooks share the same value via the event log.

## [0.7.0] - 2026-02-08

### Added
- **Cairns — episodic session memory** — new `cairns` MCP tool (#13) and `CairnManager` for setting, stacking, inspecting, and compressing session markers. Each cairn links to all memories from a session, with LLM-synthesized narrative and title. Walk the trail back on next session start — no more cold starts.
- **Hook scripts for automatic session capture** — three shell scripts in `examples/hooks/` that wire into Claude Code's lifecycle hooks:
  - `session-start.sh` (SessionStart) — fetches recent cairn context, initializes a JSONL event log for the session
  - `log-event.sh` (PostToolUse) — silently appends every tool call to the event log with compact summaries. No HTTP calls, no blocking — just a local file append. These are **motes**: tiny, ephemeral observations that accumulate naturally during a session.
  - `session-end.sh` (SessionEnd) — bundles the event stream and POSTs a cairn via REST API with all events attached
- **`POST /api/cairns`** — write endpoint for hook-based cairn creation (REST API was previously read-only)
- **`GET /api/cairns`** and **`GET /api/cairns/:id`** — REST endpoints for browsing the session trail
- **Migration 004** — `cairns` table (id, project_id, session_name, title, narrative, events JSONB, memory_count, started_at, set_at, is_compressed) + `cairn_id` FK column on `memories` table
- **`CAIRN_LLM_CAIRN_SYNTHESIS`** env var — toggleable LLM narrative generation for cairns, with graceful degradation
- 13 new unit tests for cairn functionality

### Design
- **Three-tier graceful degradation** for session capture:
  - **Tier 3 (Hook-automated):** Claude Code hooks silently capture every tool call as a mote, then crystallize the session into a cairn at exit. Zero agent effort. This is the full vision.
  - **Tier 2 (Tool-assisted):** Agent calls `cairns(action="set")` at session end. Works without hooks.
  - **Tier 1 (Organic):** Agent follows rules, stores memories with `session_name`, synthesizes manually. Works without cairns tool.
- **Motes are ephemeral by design** — they live in `/tmp` as JSONL, not in PostgreSQL. A session's motes flow into the cairn's `events` JSONB at session end, then the temp file is cleaned up. Lightweight capture, permanent crystallization.
- Set-only model — cairns are created retroactively from existing session memories, no active session tracking needed
- `cairns` table is 14th table, 4th migration. Zero breaking changes to existing schema.

## [0.6.0] - 2026-02-07

### Added
- **Query expansion** — LLM rewrites search queries with related terms and synonyms before embedding, improving recall across all three search modes
- **Relationship extraction** — on store, vector-searches for top 5 nearest neighbors and asks LLM which are genuinely related; auto-creates typed `memory_relations` entries (extends, contradicts, implements, depends_on, related)
- **Rule conflict detection** — when storing a `rule`-type memory, checks existing rules for contradictions via LLM; advisory only (rule is always stored), conflicts returned in response
- **Session synthesis** — new `synthesize` MCP tool (#11) fetches all memories for a session and produces a 2-4 paragraph narrative via LLM
- **Memory consolidation** — new `consolidate` MCP tool (#12) finds semantically similar memory pairs (>0.85 cosine), asks LLM to recommend merges/promotions/inactivations; `dry_run=True` by default
- **Confidence gating** — post-search LLM assessment of result quality; returns confidence score, best match ID, and irrelevant IDs; off by default (high reasoning demand)
- **`LLMCapabilities` config** — frozen dataclass with 6 independently toggleable feature flags, parsed from `CAIRN_LLM_*` env vars
- **Status endpoint** now reports active LLM capabilities in `llm_capabilities` field
- 6 new env vars: `CAIRN_LLM_QUERY_EXPANSION`, `CAIRN_LLM_RELATIONSHIP_EXTRACT`, `CAIRN_LLM_RULE_CONFLICT_CHECK`, `CAIRN_LLM_SESSION_SYNTHESIS`, `CAIRN_LLM_CONSOLIDATION`, `CAIRN_LLM_CONFIDENCE_GATING`
- `tests/helpers.py` — shared `MockLLM` and `ExplodingLLM` extracted from duplicated test code
- 25 new tests across 6 test files (query expansion, synthesis, relationship extraction, rule conflicts, consolidation, confidence gating)

### Changed
- `store` response now includes `auto_relations` (list) and `rule_conflicts` (list or null) fields
- `search` response wraps results with `confidence` assessment when confidence gating is active
- `SearchEngine` and `MemoryStore` constructors now accept optional `llm` and `capabilities` parameters
- `Services` dataclass expanded with `session_synthesizer` and `consolidation_engine` fields
- `prompts.py` expanded from 2 to 8 prompt templates with 8 builder functions

### Design
- Every LLM capability follows the same pattern: flag check → try LLM → catch failure → fall back to no-op
- Core functionality (store, search, recall) never depends on LLM — all LLM features are additive
- No new database migration needed — all capabilities use existing tables

## [0.5.3] - 2026-02-08

### Fixed
- **Security** — removed hardcoded database passwords from `migrate_recallium.py`; script now requires `RECALLIUM_DSN` and `CAIRN_DSN` environment variables
- **AWS credentials path** — compose volume mount comment updated from `/root/` to `/home/cairn/` for non-root container
- **LLM response parsing** — Bedrock and Ollama backends now use defensive key access instead of trusting nested response structure

### Added
- **LLM retry logic** — both Bedrock and Ollama retry up to 3 times on transient failures (throttling, timeouts, network errors) with exponential backoff
- **Consistent error handling** — all 10 MCP tools now catch runtime exceptions and return `{"error": ...}` instead of letting stack traces reach the client
- **`.dockerignore`** — excludes PDFs, archives, tests, UI, scripts from Docker build context
- **Reproducible builds** — `requirements.lock` now wired into Dockerfile (`pip install -r requirements.lock` before `pip install --no-deps .`)
- **Health check** on `cairn` service in docker-compose (hits `/api/status`)
- `CAIRN_ENRICHMENT_ENABLED` documented in `.env.example`

### Changed
- `Database._pool` renamed to `Database._conn` — it's a single connection, not a pool

## [0.5.2] - 2026-02-08

### Added
- **Input validation** on MCP tools — content size limit (100KB), string length bounds (255 chars), enum validation for `memory_type`, `action`, `search_mode`, limit clamping (max 100)
- **Non-root Docker user** — container runs as `cairn:1000` instead of root; `HF_HOME` set for model cache ownership
- **t-SNE sampling cap** — visualization randomly samples down to 500 points when memory count exceeds threshold, preventing O(n^2) OOM; response includes `sampled`, `total_memories`, `sampled_count` flags
- **Dependency lockfile** — `requirements.lock` pinned from production container for reproducible builds
- `ValidationError` exception class and `validate_store()` / `validate_search()` helpers in `cairn/core/utils.py`
- Input limit constants in `cairn/core/constants.py` (`MAX_CONTENT_SIZE`, `MAX_LIMIT`, `VALID_SEARCH_MODES`, etc.)

## [0.5.1] - 2026-02-08

### Changed
- **Services container** — new `cairn/core/services.py` with `Services` dataclass and `create_services()` factory; server.py init collapsed from 25 lines to single factory call
- **Centralized constants** — new `cairn/core/constants.py` extracts enums (`MemoryAction`, `TaskStatus`, `ThinkingStatus`) and valid-type lists from 6 scattered modules
- **Shared utilities** — new `cairn/core/utils.py` with `get_or_create_project()`, `extract_json()`, `strip_markdown_fences()` eliminating ~360 lines of duplication
- `create_api()` accepts `Services` object instead of 8 keyword arguments
- `insights` tool now calls `ClusterEngine.get_last_run()` instead of raw DB queries (layer violation fix)
- Docker Compose credentials use `${VAR:-default}` env var substitution for `.env` override

### Fixed
- Thinking sequence `conclude()` now guards against double-conclude (raises `ValueError` if already completed)

### Removed
- Dead root `server.py` (88 lines) — Docker runs `cairn.server`, not this file

## [0.5.0] - 2026-02-08

### Added
- **Memory timeline / activity feed** — `GET /api/timeline` endpoint + `/timeline` page with date-grouped cards (Today, Yesterday, older), project/type/days filters
- **Command palette (Cmd+K)** — global `Cmd+K`/`Ctrl+K` shortcut, navigation to all 8 pages + debounced memory search, mounted in root layout
- **Inline memory viewer (Sheet)** — slide-over panel shows full memory detail (content, tags, stats, cluster, metadata) without navigating away. Wired into Search and Timeline pages
- **Cluster visualization** — `GET /api/clusters/visualization` endpoint runs t-SNE on memory embeddings; canvas scatter plot at `/clusters/visualization` with cluster coloring, hover tooltips, click-to-view
- **Export** — `GET /api/export?project=&format=` endpoint returns JSON or Markdown; download button on project detail page with format dropdown
- shadcn Sheet UI component (`components/ui/sheet.tsx`)
- Timeline nav item (Clock icon, second position after Dashboard)
- Visualization link button on Clusters page

### Changed
- Search results now open inline Sheet instead of navigating to `/memories/:id`
- API version bumped to 0.5.0
- `cairn-ui` package version bumped to 0.5.0

## [0.4.3] - 2026-02-07

### Added
- **Server-side pagination** for all list endpoints — `tasks`, `thinking`, `projects`, `rules`, and `search` now accept `limit`/`offset` params and return `{total, limit, offset, items}` response shape
- UI updated to consume paginated API responses

### Fixed
- `rules` MCP tool returning wrapped `{"result": items}` instead of plain items list

### Changed
- Core methods (`get_rules`, `list_tasks`, `list_sequences`, `list_projects`) refactored for consistent paginated response shape
- MCP tools extract `items` only to preserve backward compatibility with Claude clients

## [0.4.2] - 2026-02-07

### Added
- GHCR image for cairn-ui — CI now builds and pushes `ghcr.io/jasondostal/cairn-mcp-ui` on version tags
- `server` and `ui` jobs run in parallel in CI workflow

### Changed
- `cairn-ui` in docker-compose switched from local build to GHCR image pull
- ROADMAP v0.4.x polish fully complete (7/8, only GHCR image was remaining)

## [0.4.1] - 2026-02-07

### Added
- **Active nav highlighting** — extracted `SidebarNav` component with `usePathname()` active state
- **Mobile responsive layout** — hamburger menu + backdrop drawer on small screens
- **Error states** — reusable `ErrorState` component + `useFetch` hook, applied to all pages
- **Client-side pagination** — `usePagination` hook (20 items/page) + `PaginationControls` component
- **Favicon** — SVG cairn icon, removed all default Next.js assets
- **Back-navigation** — ArrowLeft + `router.back()` on memory detail page
- **Health check** — `wget` healthcheck for `cairn-ui` in docker-compose

### Changed
- Quick Start guide updated for 3-container stack (cairn, cairn-ui, cairn-db)
- `pyproject.toml` version bumped to match release
- ROADMAP v0.4.x polish items checked off (7/8 complete)
- `cairn-ui` docker-compose switched from local build to GHCR image

### CI
- Added `ui` job to `publish.yml` — builds and pushes `ghcr.io/jasondostal/cairn-mcp-ui` on version tags

### Docs
- README overhaul with badges, highlights, architecture diagram, and better structure
- Added ROADMAP.md with v0.4.x polish and v0.5.0 feature plans

## [0.4.0] - 2026-02-07

### Added
- **Web UI** — Complete Next.js 16 + shadcn/ui + Tailwind CSS 4 dashboard (`cairn-ui/`)
- 7 pages: Dashboard, Search, Projects (list + detail), Clusters, Tasks, Thinking (list + detail), Rules
- Memory detail view (`/memories/:id`) with full content, metadata, tags, cluster context
- Typed API client (`cairn-ui/src/lib/api.ts`) covering all 10 REST endpoints
- Search page with hybrid/keyword/vector mode selector, project and type filters
- Cluster explorer with expandable sample memories and confidence scores
- Thinking sequence viewer with thought timeline, type icons, and branch visualization
- Multi-stage production Dockerfile (deps → build → standalone runner)
- `.dockerignore` for efficient Docker builds
- `cairn-ui` service in `docker-compose.yml`
- Recallium migration script (`scripts/migrate_recallium.py`)

### Fixed
- `CAIRN_API_URL` set at Docker build time so Next.js rewrites resolve correctly in standalone mode

### Infrastructure
- Reverse proxy configuration (SWAG + Authentik forward auth)
- Dark mode by default

## [0.3.0] - 2026-02-07

### Added
- Read-only REST API at `/api` for web UI consumption (`cairn/api.py`)
- 10 GET endpoints: status, search, memories, projects, clusters, tasks, thinking, rules
- FastAPI + uvicorn dependencies
- CORS middleware (permissive for dev, tighten with Authentik later)

### Changed
- HTTP mode now serves MCP at `/mcp` and REST API at `/api` on the same port
- MCP Starlette app is the parent; FastAPI mounted as sub-app
- Combined lifespan wraps DB lifecycle around MCP session manager

## [0.2.0] - 2026-02-07

### Added
- HTTP transport support via `CAIRN_TRANSPORT=http` env var (streamable-http on configurable host/port)
- `CAIRN_HTTP_HOST` and `CAIRN_HTTP_PORT` configuration
- Docker container now runs MCP server directly (replaces `tail -f /dev/null`)
- Eval framework for search quality measurement (`eval/`)
- Recall@k, precision@k, MRR, NDCG metrics (`eval/metrics.py`)
- Multi-model comparison with MODEL_REGISTRY (`eval/model_compare.py`)
- Enrichment accuracy evaluation against ground truth (`eval/enrichment_eval.py`)
- CLI runner with `--search-only`, `--models`, `--json`, `--keep-dbs` flags
- 50-memory corpus for search quality benchmarking (`eval/data/corpus.json`)
- 25 hand-labeled queries with binary relevance judgments (`eval/data/queries.json`)
- 20 annotated enrichment samples (`eval/data/enrichment_ground_truth.json`)
- Smoke tests for eval data schemas (`tests/test_eval_smoke.py`)
- 21 pure-math metric tests (`tests/test_eval_metrics.py`)

### Changed
- `.gitignore`: `data/` narrowed to `/data/` so `eval/data/` is tracked

### Verified
- Hybrid search recall@10 = 83.8% (passes PRD target of 80%)
- MiniLM-L6-v2 confirmed over all-mpnet-base-v2 (+1.5% recall, 10x embed cost)
- Keyword control check passes (identical across embedding models)

## [0.1.0] - 2026-02-07

Initial release. All four implementation phases complete.

### Phase 1: Foundation
- PostgreSQL + pgvector storage with HNSW indexing
- MiniLM-L6-v2 local embeddings (384-dim)
- Core MCP tools: `store`, `search`, `recall`, `modify`, `rules`, `status`
- Hybrid search with Reciprocal Rank Fusion (vector + keyword + tag)
- Project and session scoping

### Phase 2: Enrichment
- Automatic LLM enrichment on `store`: summary, tags, importance scoring
- AWS Bedrock backend (Llama 3.2 90B)
- Ollama local fallback
- Graceful degradation when LLM unavailable

### Phase 3: Clustering + Insights
- DBSCAN clustering on memory embeddings (eps=0.65, min_samples=3)
- LLM-generated cluster labels and summaries
- `insights` tool with lazy reclustering and staleness detection
- Topic filtering via centroid similarity
- Confidence scoring per cluster
- `recall` now includes cluster membership context

### Phase 4: Projects, Tasks, Thinking
- `projects` tool: briefs, PRDs, plans, cross-project linking
- `tasks` tool: create, complete, list, link memories to tasks
- `think` tool: structured reasoning sequences with branching
- 13 database tables across 3 migrations
- 30 tests passing (clustering, enrichment, RRF)

[Unreleased]: https://github.com/jasondostal/cairn-mcp/compare/v0.34.2...HEAD
[0.34.2]: https://github.com/jasondostal/cairn-mcp/compare/v0.34.0...v0.34.2
[0.34.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.33.0...v0.34.0
[0.33.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.31.0...v0.33.0
[0.31.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.30.1...v0.31.0
[0.30.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.29.0...v0.30.0
[0.29.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.28.2...v0.29.0
[0.28.2]: https://github.com/jasondostal/cairn-mcp/compare/v0.28.1...v0.28.2
[0.28.1]: https://github.com/jasondostal/cairn-mcp/compare/v0.28.0...v0.28.1
[0.28.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.27.2...v0.28.0
[0.27.2]: https://github.com/jasondostal/cairn-mcp/compare/v0.27.1...v0.27.2
[0.27.1]: https://github.com/jasondostal/cairn-mcp/compare/v0.27.0...v0.27.1
[0.27.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.26.0...v0.27.0
[0.26.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.25.0...v0.26.0
[0.25.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.24.0...v0.25.0
[0.24.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.23.1...v0.24.0
[0.23.1]: https://github.com/jasondostal/cairn-mcp/compare/v0.23.0...v0.23.1
[0.23.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.22.1...v0.23.0
[0.22.1]: https://github.com/jasondostal/cairn-mcp/compare/v0.22.0...v0.22.1
[0.22.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.21.0...v0.22.0
[0.21.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.20.1...v0.21.0
[0.20.1]: https://github.com/jasondostal/cairn-mcp/compare/v0.20.0...v0.20.1
[0.20.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.19.0...v0.20.0
[0.19.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.18.0...v0.19.0
[0.18.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.17.0...v0.18.0
[0.17.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/jasondostal/cairn-mcp/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.5.3...v0.6.0
[0.5.3]: https://github.com/jasondostal/cairn-mcp/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/jasondostal/cairn-mcp/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/jasondostal/cairn-mcp/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.4.3...v0.5.0
[0.4.3]: https://github.com/jasondostal/cairn-mcp/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/jasondostal/cairn-mcp/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/jasondostal/cairn-mcp/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jasondostal/cairn-mcp/releases/tag/v0.1.0
