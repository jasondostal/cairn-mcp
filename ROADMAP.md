# Roadmap

Current: **v0.7.1** — Session name alignment + mote-aware narrative synthesis.

---

## v0.7.0 — Cairns (Episodic Session Memory) ✓

Session history that builds itself.

- [x] **Cairns table + migration** — 14th table, cairn_id FK on memories, zero breaking changes
- [x] **CairnManager** — set, stack, get, compress operations
- [x] **`cairns` MCP tool (#13)** — set markers, walk the trail, inspect, compress
- [x] **REST endpoints** — GET /api/cairns, GET /api/cairns/:id, POST /api/cairns
- [x] **Hook scripts** — session-start.sh, log-event.sh, session-end.sh for Claude Code lifecycle hooks
- [x] **Motes (event stream)** — every tool call silently logged to /tmp JSONL, bundled into cairn at session end
- [x] **Three-tier degradation** — hooks → organic rules → raw memories. Each tier works without the ones above it
- [x] **LLM narrative synthesis** — cairn title and narrative generated from session memories, toggleable via env var
- [x] **13 new tests** (68 total across 13 suites)

## v0.6.0 — LLM Capabilities ✓

Make the LLM earn its keep beyond enrichment and cluster labels.

- [x] **Query expansion** — LLM rewrites search queries with related terms before embedding
- [x] **Relationship extraction** — auto-detect typed relations (extends, contradicts, implements, depends_on, related) on store
- [x] **Rule conflict detection** — advisory check for contradictions when storing rules
- [x] **Session synthesis** — new `synthesize` tool, LLM narrative from session memories
- [x] **Memory consolidation** — new `consolidate` tool, find duplicates, recommend merges/promotions
- [x] **Confidence gating** — post-search quality assessment (off by default)
- [x] **Feature flags** — `LLMCapabilities` dataclass, 6 env vars, graceful degradation on every capability
- [x] **25 new tests** across 6 test files + shared test helpers

## v0.4.x — Polish

Tighten what's already there.

- [x] **Active nav highlighting** — `SidebarNav` component, `usePathname()` active state
- [x] **Error states** — reusable `ErrorState` component + `useFetch` hook, all pages
- [x] **Pagination** — server-side `limit`/`offset` on all list endpoints + client-side `usePagination` hook + `PaginationControls`
- [x] **Favicon + branding** — SVG cairn icon, removed default Next.js assets
- [x] **Back-navigation** — ArrowLeft + `router.back()` on memory detail
- [x] **GHCR image for cairn-ui** — CI/CD builds like the MCP server image
- [x] **Health check** — `wget` healthcheck for cairn-ui in docker-compose
- [x] **Mobile responsive** — hamburger menu + backdrop drawer on small screens

## v0.5.0 — Features ✓

Make the UI worth opening every day.

- [x] **Memory timeline / activity feed** — reverse-chronological stream with date grouping, project/type/days filters
- [x] **Command palette (Cmd+K)** — global shortcut, page navigation + debounced memory search
- [x] **Inline memory viewer** — Sheet slide-over with full memory detail from search/timeline
- [x] **Cluster visualization** — t-SNE scatter plot with cluster coloring, tooltips, click-to-view
- [x] **Export** — JSON/Markdown download from project detail page

## Stretch

Nice-to-haves when the core is rock solid.

- [ ] **Temporal analysis** — track how clusters evolve between clustering runs
- [ ] **PyPI publication** — `pip install cairn-mcp`
- [ ] **Blog post / writeup** — the build story, from GRIMOIRE to Cairn

---

## Completed

### v0.7.0 — Cairns (Episodic Session Memory)
Cairns MCP tool, CairnManager, migration 004, REST endpoints (including first write endpoint), hook scripts for automatic session capture. Motes — every tool call logged as a lightweight event, crystallized into a cairn at session end. Three-tier graceful degradation. 13 new tests (68 total).

### v0.6.0 — LLM Capabilities
6 new LLM capabilities with feature flags and graceful degradation. Query expansion, relationship extraction, rule conflict detection, session synthesis, memory consolidation, confidence gating. 2 new MCP tools (12 total), 25 new tests (55 total).

### v0.1.0 — Phase 1: Core Loop
PostgreSQL + pgvector, HNSW indexing, hybrid RRF search, 6 MCP tools, Docker Compose deployment.

### v0.2.0 — Phase 2: Enrichment + Eval
LLM auto-enrichment (Bedrock + Ollama), HTTP transport, eval framework with recall@k benchmarks.

### v0.3.0 — Phase 3-5: Full Feature Set + REST API
Clustering, projects, tasks, thinking, REST API (FastAPI inside MCP Starlette), README, CHANGELOG, LICENSE.

### v0.4.0 — Web UI
Next.js 16 + shadcn/ui dashboard. 7 pages: Dashboard, Search, Projects, Clusters, Tasks, Thinking, Rules. Production Dockerfile. Authentik auth. SWAG proxy. Live at cairn.witekdivers.com.

### v0.5.0 — Features
Timeline, Cmd+K command palette, inline memory viewer (Sheet), cluster visualization (t-SNE scatter plot), project export (JSON/Markdown). 3 new API endpoints, 5 new UI pages/components.
