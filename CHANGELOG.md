# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.11.0] - 2026-02-09

### Fixed
- **Race condition in cairn set** — the agent (via MCP) and session-end hook (via REST POST) could both try to set a cairn for the same session. The first one succeeded; the second got a 409 error and its events were lost. `CairnManager.set()` now uses upsert semantics: whichever path arrives second merges its data (events, narrative re-synthesis) into the existing cairn. No more empty cairns.
- **Events deleted on POST** — `session-end.sh` deleted the event log after POSTing, even on failure. Events are now archived to `~/.cairn/events/archive/` instead of deleted.

### Added
- **Server-side event archive** — `CAIRN_EVENT_ARCHIVE_DIR` env var enables writing raw JSONL events to a file-based archive on cairn set. Docker Compose mounts a `cairn-events` volume at `/data/events` by default.
- **Setup script** — `scripts/setup-hooks.sh` interactively checks dependencies, tests Cairn connectivity, creates event directories, and generates a ready-to-paste Claude Code settings.json snippet. Includes optional pipeline test.
- **Hooks documentation overhaul** — `examples/hooks/README.md` rewritten with Quick Start guides for both Claude Code and other MCP clients, environment variable table, verification steps, troubleshooting section, and updated architecture diagram showing the upsert flow.

### Changed
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
- SWAG reverse proxy config for `cairn.witekdivers.com`
- Authentik forward auth (proxy provider, forward_single mode)
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

[Unreleased]: https://github.com/jasondostal/cairn-mcp/compare/v0.11.0...HEAD
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
