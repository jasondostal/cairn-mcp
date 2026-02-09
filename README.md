<p align="center">
  <strong>Cairn</strong><br>
  <em>Persistent memory for AI agents</em>
</p>

<p align="center">
  <a href="https://github.com/jasondostal/cairn-mcp/releases"><img src="https://img.shields.io/github/v/release/jasondostal/cairn-mcp?style=flat-square&color=blue" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/jasondostal/cairn-mcp?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/MCP-compatible-brightgreen?style=flat-square" alt="MCP">
  <img src="https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791?style=flat-square" alt="PostgreSQL">
</p>

---

An MCP server that gives AI agents persistent memory with three-tier knowledge capture: everything from deliberate decisions to ambient tool activity is remembered, organized, and surfaced automatically. Hybrid semantic search, pattern discovery, and session continuity — so agents never start from zero.

**Built for agents.** 13 MCP tools, a REST API, and a web dashboard — three containers, one `docker compose up`.

## Three-Tier Knowledge Capture

Most agent memory systems require the agent to explicitly decide what's worth remembering. Cairn captures knowledge at three levels simultaneously, with each tier working independently:

| Tier | How it works | Agent effort | What's captured |
|------|-------------|-------------|----------------|
| **Tier 3: Hook-automated** | Claude Code lifecycle hooks silently log every tool call as a *mote* (lightweight event). At session end, the full event stream is crystallized into a cairn with an LLM-synthesized narrative. | Zero | Everything — files read, edits made, commands run, searches performed |
| **Tier 2: Tool-assisted** | Agent calls `cairns(action="set")` at session end to mark a trail marker. Works without hooks. | One tool call | All memories stored during the session |
| **Tier 1: Organic** | Agent stores memories via behavioral rules — decisions, learnings, dead ends. Works without cairns. | Per-insight | Deliberate observations the agent deems important |

The tiers are additive and degrade gracefully. With all three active, a session produces: a rich narrative synthesized from both the mote timeline *and* stored memories, linked trail markers for next session's context, and individually searchable memories with auto-enrichment. Remove the hooks? Tier 2 and 1 still work. Agent forgets to set a cairn? The organic memories are still there.

**Next session, the agent walks the trail back.** Session-start hooks load recent cairn narratives into context — the agent picks up where the last one left off, not from a blank slate.

## Highlights

- **Three-tier capture** — Ambient motes + session cairns + organic memories. See above.
- **Hybrid search** — Vector similarity + full-text + tag matching, fused with Reciprocal Rank Fusion. [83.8% recall@10](#search-quality) on our internal benchmark (50-memory synthetic corpus, 25 hand-labeled queries). Optional LLM query expansion.
- **Auto-enrichment** — Every memory gets an LLM-generated summary, tags, and importance score on store. Bedrock or Ollama.
- **Smart relationships** — On store, LLM identifies genuinely related memories and creates typed links (extends, contradicts, implements, depends_on). Rule conflict detection warns about contradictions.
- **Pattern discovery** — DBSCAN clustering finds themes across memories. LLM writes the labels. No cron jobs — clusters refresh lazily.
- **Session continuity** — Cairns mark the trail. Motes capture what happened. Narratives synthesize why it mattered. Next session starts with context, not a cold start.
- **Memory consolidation** — Find duplicates, recommend merges and promotions, with dry-run safety.
- **Structured thinking** — Reasoning sequences with branching, for when an agent needs to think through a problem step by step.
- **Web dashboard** — Next.js + shadcn/ui. Timeline, search, cluster visualization, knowledge graph, Cmd+K command palette, inline memory viewer. Dark mode.
- **One port, everything** — MCP protocol at `/mcp`, REST API at `/api`, same process. stdio also supported.
- **Hardened** — Input validation on all tools, non-root Docker container, t-SNE sampling cap, pinned dependencies.
- **6 LLM capabilities** — Each independently toggleable via env vars, each with graceful degradation. Core search/store/cairns never depends on LLM.

## MCP Tools

| Tool | What it does |
|------|-------------|
| `store` | Persist a memory with auto-enrichment, relationship extraction, and rule conflict detection |
| `search` | Hybrid semantic search with query expansion and optional confidence gating |
| `recall` | Expand memory IDs to full content with cluster context |
| `modify` | Update, soft-delete, or reactivate memories |
| `rules` | Behavioral guardrails — global or per-project |
| `insights` | DBSCAN clustering with LLM-generated pattern summaries |
| `projects` | Documents (briefs, PRDs, plans) and cross-project linking |
| `tasks` | Task lifecycle — create, complete, list, link to memories |
| `think` | Structured reasoning sequences with branching |
| `status` | System health, counts, embedding model info, active LLM capabilities |
| `synthesize` | Synthesize session memories into a coherent narrative |
| `consolidate` | Find duplicate memories, recommend merges/promotions/inactivations |
| `cairns` | Session markers — set at session end, walk the trail back, compress old ones |

## Architecture

```
Browser                   MCP Client (Claude, etc.)         curl / scripts
   |                          |                                  |
   | HTTPS                    | stdio or streamable-http         | REST (GET)
   |                          |                                  |
+--v---+                  +---v----------------------------------v-----------+
| Next | --/api proxy-->  |  /mcp  (MCP protocol)          /api  (REST API)  |
| .js  |                  |                                                   |
| UI   |                  |  cairn.server  (MCP tool definitions)             |
+------+                  |  cairn.api     (read-only FastAPI endpoints)      |
cairn-ui                  |                                                   |
                          |  core: memory, search, enrichment, clustering     |
                          |        projects, tasks, thinking, cairns          |
                          |        synthesis, consolidation                   |
                          |                                                   |
                          |  embedding: MiniLM-L6-v2 (local, 384-dim)        |
                          |  llm: Bedrock (Llama 90B) or Ollama (local)       |
                          |  storage: PostgreSQL 16 + pgvector (HNSW)        |
                          +---------------------------------------------------+
                              |
                              v
                          PostgreSQL 16 + pgvector (14 tables, 4 migrations)
```

## Prerequisites

Cairn needs an **LLM backend** for enrichment, relationship extraction, and session narrative synthesis. Choose one:

| Backend | Setup | Best for |
|---------|-------|----------|
| **Ollama** (default) | Install [Ollama](https://ollama.com), pull a model (`ollama pull qwen2.5-coder:7b`). Cairn connects to `host.docker.internal:11434`. | Local development, no cloud dependency |
| **AWS Bedrock** | Set `CAIRN_LLM_BACKEND=bedrock`, mount or export AWS credentials. Requires model access in your AWS account. | Production, larger models |

**No LLM? Cairn still works.** Core features — store, search, recall, cairns, rules — function without an LLM. You lose auto-enrichment (summaries, tags, importance scoring), relationship extraction, and session narrative synthesis. Memories are still embedded and searchable.

> **Security note:** The default `docker-compose.yml` ships with a development database password (`cairn-dev-password`). This is intentional for quick local setup. For any network-exposed deployment, override it: `CAIRN_DB_PASS=your-secure-password docker compose up -d`

## Quick Start

### 1. Pull and run

```bash
curl -O https://raw.githubusercontent.com/jasondostal/cairn-mcp/main/docker-compose.yml
docker compose up -d
```

This starts three containers:
- **cairn** — MCP server + REST API on port 8000
- **cairn-ui** — Web dashboard on port 3000
- **cairn-db** — PostgreSQL 16 with pgvector

Migrations run automatically. Ready in under a minute.

<details>
<summary>docker-compose.yml</summary>

```yaml
services:
  cairn:
    image: ghcr.io/jasondostal/cairn-mcp:latest
    container_name: cairn
    restart: unless-stopped
    environment:
      CAIRN_DB_HOST: "${CAIRN_DB_HOST:-cairn-db}"
      CAIRN_DB_PORT: "${CAIRN_DB_PORT:-5432}"
      CAIRN_DB_NAME: "${CAIRN_DB_NAME:-cairn}"
      CAIRN_DB_USER: "${CAIRN_DB_USER:-cairn}"
      CAIRN_DB_PASS: "${CAIRN_DB_PASS:-cairn-dev-password}"
      CAIRN_LLM_BACKEND: "${CAIRN_LLM_BACKEND:-ollama}"
      CAIRN_BEDROCK_MODEL: "${CAIRN_BEDROCK_MODEL:-us.meta.llama3-2-90b-instruct-v1:0}"
      CAIRN_OLLAMA_URL: "${CAIRN_OLLAMA_URL:-http://host.docker.internal:11434}"
      CAIRN_OLLAMA_MODEL: "${CAIRN_OLLAMA_MODEL:-qwen2.5-coder:7b}"
      CAIRN_TRANSPORT: "${CAIRN_TRANSPORT:-http}"
    ports:
      - "${CAIRN_HTTP_PORT:-8000}:8000"
    # Uncomment to mount AWS credentials for Bedrock:
    # volumes:
    #   - ~/.aws/credentials:/home/cairn/.aws/credentials:ro
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/status')\""]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s
    depends_on:
      cairn-db:
        condition: service_healthy

  cairn-ui:
    image: ghcr.io/jasondostal/cairn-mcp-ui:latest
    container_name: cairn-ui
    restart: unless-stopped
    environment:
      CAIRN_API_URL: http://cairn:8000
    ports:
      - "${CAIRN_UI_PORT:-3000}:3000"
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:3000/ || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 10s
    depends_on:
      - cairn

  cairn-db:
    image: pgvector/pgvector:pg16
    container_name: cairn-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: "${CAIRN_DB_NAME:-cairn}"
      POSTGRES_USER: "${CAIRN_DB_USER:-cairn}"
      POSTGRES_PASSWORD: "${CAIRN_DB_PASS:-cairn-dev-password}"
    volumes:
      - cairn-pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cairn"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  cairn-pgdata:
```

</details>

### 2. Connect your agent

**Claude Code** (HTTP — recommended):

```bash
claude mcp add --transport http cairn http://localhost:8000/mcp
```

Or add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "cairn": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

**Other MCP clients** (stdio — single-client, same host):

```json
{
  "mcpServers": {
    "cairn": {
      "command": "docker",
      "args": ["exec", "-i", "cairn", "python", "-m", "cairn.server"]
    }
  }
}
```

### 3. Store your first memory

Once connected, your agent can immediately use all 13 tools. Try:

> "Remember that we chose PostgreSQL with pgvector for the storage layer because it gives us hybrid search without a separate vector database."

Cairn will store it, generate a summary, auto-tag it, and score its importance.

### 4. Enable session capture (optional)

Cairn can automatically capture your entire session — every tool call logged as a lightweight event (*mote*), crystallized into a cairn when the session ends. Next session, the agent starts with context instead of a blank slate.

Add hooks to your project's `.claude/settings.local.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "CAIRN_URL=http://localhost:8000 /path/to/cairn/examples/hooks/session-start.sh",
            "timeout": 15
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/cairn/examples/hooks/log-event.sh",
            "timeout": 5
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "CAIRN_URL=http://localhost:8000 /path/to/cairn/examples/hooks/session-end.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Replace `/path/to/cairn` with wherever you cloned the repo. Set `CAIRN_URL` to your Cairn instance. `CAIRN_PROJECT` defaults to the working directory name — override it if you want a different project name.

**What happens:**
1. **Session starts** — hook fetches recent cairns for context, creates an event log in `~/.cairn/events/`
2. **Every tool call** — hook appends a one-line JSON event to the log (local file, no HTTP, no blocking)
3. **Session ends** — hook bundles all events and POSTs a cairn with the full event stream

Override the event log directory with `CAIRN_EVENT_DIR`. Requires `jq` and `curl`.

No hooks? No problem. The `cairns` tool works without them — the agent can call `cairns(action="set")` directly. And even without cairns, memories stored with a `session_name` are still grouped and searchable.

## REST API

Read-only endpoints at `/api` — powers the web UI and works great for scripting.

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | System health, memory counts, cluster info |
| `GET /api/search?q=&project=&type=&mode=&limit=` | Hybrid search |
| `GET /api/memories/:id` | Single memory with cluster context |
| `GET /api/projects` | All projects with memory counts |
| `GET /api/projects/:name` | Project docs and links |
| `GET /api/clusters?project=&topic=` | Clusters with member lists |
| `GET /api/tasks?project=` | Tasks for a project |
| `GET /api/thinking?project=&status=` | Thinking sequences |
| `GET /api/thinking/:id` | Sequence detail with all thoughts |
| `GET /api/rules?project=` | Behavioral rules |
| `GET /api/timeline?project=&type=&days=` | Memory activity feed |
| `GET /api/cairns?project=` | Session trail — cairns newest first |
| `GET /api/cairns/:id` | Single cairn with linked memories |
| `GET /api/clusters/visualization?project=` | t-SNE 2D coordinates for scatter plot |
| `GET /api/export?project=&format=` | Export project memories (JSON or Markdown) |

```bash
curl http://localhost:8000/api/status
curl "http://localhost:8000/api/search?q=architecture&limit=5"
```

## Web UI

A full dashboard for browsing your agent's memory. Built with Next.js 16, shadcn/ui, and Tailwind CSS 4.

**9 pages:** Dashboard / Timeline / Search / Projects / Clusters / Cluster Visualization / Tasks / Thinking / Rules

**Plus:** Cmd+K command palette (global), inline memory viewer (Sheet slide-over), project export

The UI runs as a separate container and proxies API calls to the Cairn backend.

```bash
docker compose up -d  # starts cairn, cairn-db, and cairn-ui
```

Or run in development:

```bash
cd cairn-ui
npm install
CAIRN_API_URL=http://localhost:8000 npm run dev
```

## Search

Cairn fuses three signals with **Reciprocal Rank Fusion (RRF)**:

| Signal | Weight | How |
|--------|--------|-----|
| Vector similarity | 60% | Cosine distance on MiniLM-L6-v2 embeddings via pgvector HNSW |
| Keyword search | 25% | PostgreSQL `ts_rank` full-text search |
| Tag matching | 15% | Intersection of query-derived tags with memory tags |

Filter by project, memory type, file path, recency, or set custom limits. Three modes: `semantic` (hybrid, default), `keyword`, or `vector`.

## Configuration

All via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_DB_HOST` | `cairn-db` | PostgreSQL host |
| `CAIRN_DB_PORT` | `5432` | PostgreSQL port |
| `CAIRN_DB_NAME` | `cairn` | Database name |
| `CAIRN_DB_USER` | `cairn` | Database user |
| `CAIRN_DB_PASS` | *(required)* | Database password |
| `CAIRN_LLM_BACKEND` | `ollama` | `ollama` or `bedrock` |
| `CAIRN_BEDROCK_MODEL` | `us.meta.llama3-2-90b-instruct-v1:0` | Bedrock model ID |
| `CAIRN_OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama API URL |
| `CAIRN_OLLAMA_MODEL` | `qwen2.5-coder:7b` | Ollama model name |
| `CAIRN_TRANSPORT` | `stdio` | `stdio` or `http` |
| `CAIRN_HTTP_HOST` | `0.0.0.0` | HTTP bind address |
| `CAIRN_HTTP_PORT` | `8000` | HTTP listen port |
| `CAIRN_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |
| `CAIRN_LLM_QUERY_EXPANSION` | `true` | Expand search queries with related terms |
| `CAIRN_LLM_RELATIONSHIP_EXTRACT` | `true` | Auto-detect relationships between memories on store |
| `CAIRN_LLM_RULE_CONFLICT_CHECK` | `true` | Check new rules for conflicts with existing rules |
| `CAIRN_LLM_SESSION_SYNTHESIS` | `true` | Enable session narrative synthesis |
| `CAIRN_LLM_CONSOLIDATION` | `true` | Enable memory consolidation recommendations |
| `CAIRN_LLM_CONFIDENCE_GATING` | `false` | Post-search quality assessment — returns a confidence score but does not filter results (caller decides). High reasoning demand. |

## Development

```bash
git clone https://github.com/jasondostal/cairn-mcp.git
cd cairn-mcp
cp .env.example .env   # edit with your settings
docker compose up -d --build
```

### Testing

68 tests across 13 suites:

```bash
docker exec cairn pip install pytest
docker cp tests/ cairn:/app/tests/
docker exec cairn python -m pytest tests/ -v
```

### Database Schema

14 tables across 4 migrations:

| Migration | Tables |
|-----------|--------|
| **001 Core** | `projects`, `memories`, `memory_related_files`, `memory_related_memories` |
| **002 Clustering** | `clusters`, `cluster_members`, `clustering_runs` |
| **003 Phase 4** | `project_documents`, `project_links`, `tasks`, `task_memory_links`, `thinking_sequences`, `thoughts` |
| **004 Cairns** | `cairns` + `cairn_id` FK on `memories` |

## Search Quality

Cairn includes an evaluation framework (`eval/`) for measuring search quality. Current results on our internal benchmark:

| Metric | Score |
|--------|-------|
| Recall@10 | 83.8% |
| Precision@5 | 72.0% |
| MRR | 0.81 |
| NDCG@10 | 0.78 |

**Methodology and limitations:**

- **Corpus:** 50 synthetic memories, fabricated to cover diverse topic areas. Not derived from real usage data.
- **Queries:** 25 hand-labeled queries with binary relevance judgments (relevant / not relevant), authored by the developer.
- **No graded relevance** — a partially-relevant result scores the same as irrelevant (0). This inflates recall and obscures ranking quality.
- **No error bars** — 25 queries is a small sample. The true recall likely has a wide confidence interval.
- **Small corpus effect** — with 50 memories and a candidate pool of `limit * 5`, the system examines a significant fraction of the entire corpus before ranking. Performance at 500+ memories is untested.
- **RRF weights** (vector 60%, keyword 25%, tag 15%) and `k=60` are based on initial tuning, not exhaustive ablation.

The eval runs **without LLM features** (no query expansion, no confidence gating) — results reflect base search quality only. Query expansion's impact on recall has not been measured separately.

The eval framework supports model comparison (MiniLM-L6-v2 vs. all-mpnet-base-v2 evaluated, smaller model chosen with +1.5% recall advantage) and includes a keyword-only control to isolate embedding quality.

We plan to grow the corpus, add graded relevance, test query expansion impact, and measure at larger scales. Contributions to the eval set are welcome.

## License

[GNU General Public License v3.0](LICENSE)
