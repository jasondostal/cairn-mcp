# Roadmap

Current: **v0.18.0** — Pluggable providers, API auth, UI polish.

---

## v0.18.0 — Open Architecture + Dashboard Polish ✓

Bring your own LLM. Lock down the API. Make the dashboard feel alive.

- [x] **Pluggable LLM providers** — factory + registry pattern. Built-in: Ollama, Bedrock, Gemini, OpenAI-compatible (covers Groq, Together, Mistral, LM Studio, vLLM). Custom providers via `register_llm_provider()`.
- [x] **Pluggable embedding providers** — same factory/registry pattern. Built-in: local SentenceTransformer.
- [x] **Optional API key auth** — lightweight middleware, off by default. Configurable header for auth proxy compatibility (Authentik, Caddy, nginx). Health/swagger endpoints exempt. MCP unaffected.
- [x] **Memory relations in API** — search results and memory detail include incoming/outgoing relationship data
- [x] **Search score transparency** — vector/keyword/tag score components exposed per result
- [x] **Thinking tree visualization** — hierarchical tree with collapsible branches, color-coded thought types
- [x] **Keyboard navigation** — j/k and arrow keys on Search/Timeline, Enter to open, Esc to clear
- [x] **Activity heatmap** — 52-day GitHub-style contribution graph on Timeline
- [x] **Dense/compact views** — toggle on Docs, Tasks, Timeline pages
- [x] **Toast notifications** — Sonner-based feedback for background operations
- [x] **Capture inline entities** — @mentions → project, #hashtags → tags, URLs → URL field
- [x] **Search score breakdown hover** — color-coded vector/keyword/tag contribution tooltip
- [x] **Next.js auth middleware** — API key injected server-side on proxied requests

## v0.17.0 — Human Capture Surfaces ✓

Agents remember. Now humans can too.

- [x] **Capture UI** — `/capture` page with slash commands, keyboard-first, remembers last project
- [x] **URL extraction** — paste a URL, get readable text via trafilatura
- [x] **Browser bookmarklet** — one-click capture from any page
- [x] **iOS Shortcut support** — share sheet → Cairn
- [x] **Memory type on ingest** — thread `memory_type` through the full pipeline

## v0.16.0 — Smart Ingestion Pipeline ✓

One endpoint, many doorways.

- [x] **Unified `POST /api/ingest`** — classify, chunk, dedup, route in one call
- [x] **Chonkie chunking** — markdown-aware splitting for large documents
- [x] **LLM content classification** — auto-route to doc, memory, or both
- [x] **Content-hash dedup** — idempotent re-ingestion
- [x] **Chunk→doc linkage** — `source_doc_id` traces chunks back to parent

## v0.15.0 — Content Ingestion Endpoints ✓

REST write endpoints for humans and scripts.

- [x] **`POST /api/ingest/doc`** — single document creation
- [x] **`POST /api/ingest/docs`** — batch document creation with partial success
- [x] **`POST /api/ingest/memory`** — store memory via REST (full pipeline)

## v0.14.0 — Docs Browser ✓

Read your docs without leaving Cairn.

- [x] **Docs browser** — `/docs` list + detail with rendered markdown (GFM tables, task lists)
- [x] **Expanded doc types** — primer, writeup, guide added to brief/prd/plan
- [x] **Document titles** — migration 007, auto-fallback to first heading
- [x] **Swagger moved** — `/docs` → `/swagger` to avoid collision

## v0.13.0 — Organic Memory Correction ✓

Memories aren't stale because they're old — they're stale because something newer says they're wrong.

- [x] **Contradiction escalation on store** — high-importance contradictions surfaced in `conflicts` response field
- [x] **Contradiction-aware search ranking** — contradicted memories penalized 0.5x across all search modes
- [x] **Thinking conclusion dupe rule** — global rule prevents storing conclusion text as separate memories
- [x] **7 new tests** (94 total across 16 suites)

## v0.12.0 — Event Pipeline v2 ✓

CAPTURE → SHIP → DIGEST → CRYSTALLIZE. Events flow, not batch.

- [x] **Streaming event ingestion** — `POST /api/events/ingest` accepts batches of 25, idempotent upsert, 202 Accepted
- [x] **DigestWorker** — background daemon thread digests event batches into rolling LLM summaries
- [x] **Digest-aware cairn synthesis** — narratives built from pre-digested summaries instead of raw events
- [x] **Migration 006** — `session_events` table with partial index for undigested batch polling
- [x] **Hook rewrite** — dumb pipe capture (full tool_input + tool_response), incremental shipping, `.offset` sidecar
- [x] **Pipeline v1 fallback** — old hooks still work, new hooks degrade gracefully against old server
- [x] **`CAIRN_LLM_EVENT_DIGEST`** — independently toggleable via env var
- [x] **17 new tests** (87 total across 14 suites)

## v0.11.0 — Upsert Cairns + Event Archive ✓

No more race conditions. No more lost events.

- [x] **Cairn upsert semantics** — agent and hook can both set a cairn for the same session, second merges into first
- [x] **Server-side event archive** — `CAIRN_EVENT_ARCHIVE_DIR` env var for file-based JSONL archive
- [x] **Setup script** — `scripts/setup-hooks.sh` for interactive hook installation
- [x] **Hooks documentation overhaul** — rewritten README with Quick Start, troubleshooting, architecture diagram

## v0.10.0 — Knowledge Graph ✓

See the shape of your memory.

- [x] **Knowledge graph visualization** — d3-force interactive graph at `/graph`, nodes by type, edges by relation
- [x] **Graph REST endpoint** — `GET /api/graph` with project and relation_type filters
- [x] **Cluster UX improvements** — better card layout, expandable samples, improved scatter plot

## v0.9.0 — Hardening ✓

Stand taller. Fix what the red team found.

- [x] **Connection pooling** — `psycopg_pool.ConnectionPool` with thread-local tracking, auto-recovery from INERROR state
- [x] **Configurable CORS** — `CAIRN_CORS_ORIGINS` env var, defaults to `*`, lock down behind reverse proxy
- [x] **Default LLM → Ollama** — free, local, runs on commodity hardware. Bedrock still supported.
- [x] **Persistent event logs** — `~/.cairn/events/` via `CAIRN_EVENT_DIR` instead of `/tmp`
- [x] **Eval transparency** — qualified 83.8% recall claim, documented methodology and limitations
- [x] **RRF documentation** — k=60 origin, weight rationale, candidate pool inflation noted
- [x] **Hook port fix** — 8002 → 8000

## v0.8.0 — Cairns UI + Backend Hygiene ✓

Cairns in the browser. Cross-project orientation at boot.

- [x] **Cairns UI page** — timeline view in cairn-ui with narrative, memory count, compress action
- [x] **All-projects filter** — cairn stack, task list, and thinking sequences accept optional project (omit = all)
- [x] **`get_project()` read-only lookup** — no phantom project creation on read paths
- [x] **Migration 005** — partial indexes for performance
- [x] **Cross-project boot** — session-start hook fetches cairns across all projects, not just active

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
