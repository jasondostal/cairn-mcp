# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- ROADMAP v0.4.x polish items checked off (6/8 complete, GHCR image remaining)

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

[Unreleased]: https://github.com/jasondostal/cairn-mcp/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/jasondostal/cairn-mcp/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jasondostal/cairn-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jasondostal/cairn-mcp/releases/tag/v0.1.0
