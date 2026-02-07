# Roadmap

Current: **v0.4.0** — All 5 PRD phases complete + web UI live.

---

## v0.4.x — Polish

Tighten what's already there.

- [ ] **Active nav highlighting** — sidebar should indicate the current page
- [ ] **Error states** — show proper error UI when API calls fail (not just empty pages)
- [ ] **Pagination** — projects, rules, tasks, and search results need paging for large datasets
- [ ] **Favicon + branding** — replace default Next.js icon
- [ ] **Back-navigation** — memory detail needs a way back to search results
- [ ] **GHCR image for cairn-ui** — CI/CD builds like the MCP server image
- [ ] **Health check** — add healthcheck to cairn-ui in docker-compose
- [ ] **Mobile responsive** — sidebar breaks on small screens, needs collapsible/drawer layout

## v0.5.0 — Features

Make the UI worth opening every day.

- [ ] **Memory timeline / activity feed** — "what did my agent store today?" reverse-chronological stream with filters
- [ ] **Command palette (Cmd+K)** — quick search from anywhere in the UI (command component already installed)
- [ ] **Inline memory viewer** — click a search result, slide-over panel shows detail without navigating away
- [ ] **Cluster visualization** — 2D scatter plot (t-SNE or UMAP reduced) showing how memories relate spatially
- [ ] **Export** — download a project's memories as JSON or markdown

## Stretch

Nice-to-haves when the core is rock solid.

- [ ] **Temporal analysis** — track how clusters evolve between clustering runs
- [ ] **PyPI publication** — `pip install cairn-mcp`
- [ ] **Blog post / writeup** — the build story, from GRIMOIRE to Cairn

---

## Completed

### v0.1.0 — Phase 1: Core Loop
PostgreSQL + pgvector, HNSW indexing, hybrid RRF search, 6 MCP tools, Docker Compose deployment.

### v0.2.0 — Phase 2: Enrichment + Eval
LLM auto-enrichment (Bedrock + Ollama), HTTP transport, eval framework with recall@k benchmarks.

### v0.3.0 — Phase 3-5: Full Feature Set + REST API
Clustering, projects, tasks, thinking, REST API (FastAPI inside MCP Starlette), README, CHANGELOG, LICENSE.

### v0.4.0 — Web UI
Next.js 16 + shadcn/ui dashboard. 7 pages: Dashboard, Search, Projects, Clusters, Tasks, Thinking, Rules. Production Dockerfile. Authentik auth. SWAG proxy. Live at cairn.witekdivers.com.
