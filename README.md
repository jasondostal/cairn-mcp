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

An MCP server that gives LLMs persistent, searchable, pattern-discovering memory with session history. Store anything, find it later through hybrid semantic search, mark sessions as trail markers, and let clustering surface patterns you didn't know were there.

**Built for agents.** 13 MCP tools, a REST API, and a web dashboard — all from a single container.

## Highlights

- **Hybrid search** — Vector similarity + full-text + tag matching, fused with Reciprocal Rank Fusion. 83.8% recall@10 on our eval benchmark. Optional LLM query expansion and confidence gating.
- **Auto-enrichment** — Every memory gets an LLM-generated summary, tags, and importance score on store. Bedrock or Ollama.
- **Smart relationships** — On store, LLM identifies genuinely related memories and creates typed links (extends, contradicts, implements, depends_on). Rule conflict detection warns about contradictions.
- **Pattern discovery** — DBSCAN clustering finds themes across memories. LLM writes the labels. No cron jobs — clusters refresh lazily.
- **Session memory (cairns)** — Set a marker at the end of a session. Next session, walk the trail back. LLM synthesizes a narrative for each cairn. No more cold starts.
- **Session synthesis** — Synthesize all memories from a session into a coherent narrative.
- **Memory consolidation** — Find duplicates, recommend merges and promotions, with dry-run safety.
- **Structured thinking** — Reasoning sequences with branching, for when an agent needs to think through a problem step by step.
- **Web dashboard** — Next.js + shadcn/ui. Timeline, search, cluster visualization, Cmd+K command palette, inline memory viewer. Dark mode.
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
                          |  llm: Bedrock (Llama 90B) / Ollama fallback      |
                          |  storage: PostgreSQL 16 + pgvector (HNSW)        |
                          +---------------------------------------------------+
                              |
                              v
                          PostgreSQL 16 + pgvector (14 tables, 4 migrations)
```

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

Migrations run automatically. The UI builds from source on first `up` (takes ~1 min). Ready in seconds after that.

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
| `CAIRN_LLM_BACKEND` | `bedrock` | `bedrock` or `ollama` |
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
| `CAIRN_LLM_CONFIDENCE_GATING` | `false` | Post-search result quality assessment (high reasoning demand) |

## Development

```bash
git clone https://github.com/jasondostal/cairn-mcp.git
cd cairn-mcp
cp .env.example .env   # edit with your settings
docker compose up -d --build
```

### Testing

68 tests across 10 suites:

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

## License

[GNU General Public License v3.0](LICENSE)
