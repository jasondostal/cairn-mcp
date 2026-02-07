# Cairn

Semantic memory for AI agents. An MCP server that gives LLMs persistent, searchable, pattern-discovering memory backed by PostgreSQL + pgvector.

## What It Does

Cairn stores memories with automatic semantic enrichment (summaries, tags, importance scoring via LLM), embeds them for vector search, clusters them to discover patterns, and exposes it all through 10 MCP tools that any compatible AI agent can use.

**10 MCP Tools:**

| Tool | Purpose |
|------|---------|
| `store` | Store a memory with auto-enrichment (summary, tags, importance) |
| `search` | Hybrid search: vector similarity + keyword + tag matching with RRF fusion |
| `recall` | Expand memory IDs to full content with cluster context |
| `modify` | Update, inactivate, or reactivate memories |
| `rules` | Retrieve behavioral rules (global or per-project) |
| `insights` | DBSCAN clustering with LLM-generated pattern summaries |
| `projects` | Project documents (briefs, PRDs, plans) and cross-project linking |
| `tasks` | Task lifecycle: create, complete, list, link memories |
| `think` | Structured reasoning sequences with branching |
| `status` | System health: memory counts, embedding stats, cluster info |

## Architecture

```
MCP Client (Claude, etc.)
    |
    | stdio (docker exec -i cairn python -m cairn.server)
    |
+---v----------------------------------------------+
|  cairn.server  (MCP tool definitions)            |
|                                                  |
|  cairn.core.memory      - store / recall         |
|  cairn.core.search      - hybrid RRF search      |
|  cairn.core.enrichment  - LLM auto-enrichment    |
|  cairn.core.clustering  - DBSCAN patterns        |
|  cairn.core.projects    - docs & linking          |
|  cairn.core.tasks       - task lifecycle          |
|  cairn.core.thinking    - structured reasoning    |
|                                                  |
|  cairn.embedding.engine - MiniLM-L6-v2 (local)   |
|  cairn.llm.bedrock      - Llama 90B via Bedrock   |
|  cairn.llm.ollama       - Local Ollama fallback   |
|  cairn.storage.database - PostgreSQL + pgvector   |
+--------------------------------------------------+
    |
    v
PostgreSQL 16 + pgvector (13 tables, HNSW indexing)
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- AWS credentials (for Bedrock enrichment) or Ollama (local fallback)

### 1. Get the compose file

```bash
curl -O https://raw.githubusercontent.com/jasondostal/cairn-mcp/main/docker-compose.yml
```

### 2. Start services

```bash
docker compose up -d
```

This pulls the pre-built image from GHCR and starts:
- **cairn**: The MCP server container (Python 3.11, MiniLM-L6-v2 embedded)
- **cairn-db**: PostgreSQL 16 with pgvector extension

Migrations run automatically on first start.

### 3. Connect your MCP client

Add to your MCP client configuration (e.g. Claude Desktop `claude_desktop_config.json`):

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

## Development

For contributors who want to build from source:

```bash
git clone https://github.com/jasondostal/cairn-mcp.git
cd cairn-mcp
cp .env.example .env
# Edit .env with your settings

# Build and run locally (replace "image:" with "build: ." in docker-compose.yml)
docker compose up -d --build
```

## Configuration

All configuration via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_DB_HOST` | `cairn-db` | PostgreSQL host |
| `CAIRN_DB_PORT` | `5432` | PostgreSQL port |
| `CAIRN_DB_NAME` | `cairn` | Database name |
| `CAIRN_DB_USER` | `cairn` | Database user |
| `CAIRN_DB_PASS` | (required) | Database password |
| `CAIRN_LLM_BACKEND` | `bedrock` | LLM backend: `bedrock` or `ollama` |
| `CAIRN_BEDROCK_MODEL` | `us.meta.llama3-2-90b-instruct-v1:0` | Bedrock model ID |
| `CAIRN_OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama API URL |
| `CAIRN_OLLAMA_MODEL` | `qwen2.5-coder:7b` | Ollama model name |
| `CAIRN_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |

## Search

Cairn uses **Reciprocal Rank Fusion (RRF)** to combine three search signals:

1. **Vector similarity** (60%) - cosine distance on MiniLM-L6-v2 embeddings via pgvector HNSW
2. **Keyword search** (25%) - PostgreSQL full-text search with `ts_rank`
3. **Tag matching** (15%) - intersection of query-derived tags with memory tags

Results are fused and re-ranked. Supports filtering by project, memory type, file path, recency, and custom limits.

## Clustering

The `insights` tool runs **DBSCAN** clustering on memory embeddings:

- **Lazy reclustering**: No background jobs. Clusters are refreshed when stale (>24h, >20% memory growth, or no prior run).
- **LLM summaries**: Each cluster gets a human-readable label and summary via LLM. Falls back to generic labels if LLM is unavailable.
- **Topic filtering**: Pass a `topic` parameter to find clusters semantically similar to your query.
- **Confidence scoring**: Based on cluster tightness (inverse of average distance from centroid).

Parameters: `eps=0.65`, `min_samples=3`, cosine metric. Calibrated for MiniLM-L6-v2 embedding space.

## Testing

```bash
# Install test dependencies
docker exec cairn pip install pytest

# Copy tests into container
docker cp tests/ cairn:/app/tests/

# Run all tests
docker exec cairn python -m pytest tests/ -v
```

30 tests across 3 suites: clustering (12), enrichment (10), RRF search (8).

## Database Schema

13 tables across 3 migrations:

**Core (001):** `projects`, `memories`, `memory_related_files`, `memory_related_memories`
**Clustering (002):** `clusters`, `cluster_members`, `clustering_runs`
**Phase 4 (003):** `project_documents`, `project_links`, `tasks`, `task_memory_links`, `thinking_sequences`, `thoughts`

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
