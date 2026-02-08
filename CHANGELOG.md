# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/jasondostal/cairn-mcp/compare/v0.7.0...HEAD
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
