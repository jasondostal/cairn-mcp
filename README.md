<p align="center">
  <img src="images/cairn-readme-banner.png" alt="Cairn — persistent memory for agents and humans" width="800">
</p>

<p align="center">
  <a href="https://github.com/jasondostal/cairn-mcp/releases"><img src="https://img.shields.io/github/v/release/jasondostal/cairn-mcp?style=flat-square&color=blue" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/jasondostal/cairn-mcp?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/MCP-compatible-brightgreen?style=flat-square" alt="MCP">
  <img src="https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791?style=flat-square" alt="PostgreSQL">
</p>

---

A self-hosted persistent memory platform for AI agents and humans. Store something once, find it later, across sessions, across projects. Four containers. `docker compose up`. Done.

Cairn is the memory brain. Your agent runtime handles execution — Cairn handles knowing. What decisions were made, what facts are known, what patterns emerge across projects.

It's built for the systems person. The curious. The t-shaped. The ones who need a memory that works the way they do, across everything, all at once.

## Quick Start

### 1. Pull and run

```bash
curl -O https://raw.githubusercontent.com/jasondostal/cairn-mcp/main/docker-compose.yml
docker compose up -d
```

Four containers start:
- **cairn** on port 8000 (MCP server + REST API)
- **cairn-ui** on port 3000 (web dashboard)
- **cairn-db** (PostgreSQL 16 + pgvector)
- **cairn-graph** (Neo4j 5, knowledge graph)

Migrations run on first boot. Ready in about a minute.

### 2. Connect your IDE

Add this to your MCP config:

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

Where that goes:

| IDE | Config file |
|-----|------------|
| **Claude Code** | `.mcp.json` in your project root |
| **Cursor** | `.cursor/mcp.json` |
| **Windsurf** | `.windsurf/mcp.json` |
| **Cline** | MCP settings panel in VS Code |
| **Continue** | `.continue/config.yaml` |
| **PiClaw** | `.pi/mcp.json` |

Or run the setup wizard — it walks you through everything: LLM backend, database, embeddings, auth, and IDE configuration:

```bash
git clone https://github.com/jasondostal/cairn-mcp.git && ./cairn-mcp/scripts/setup.sh
```

Pick a tier (local dev, recommended, enterprise, or custom) and the wizard collects only what that tier needs. Supports `--dry-run` and `--non-interactive` for CI.

### 3. Use it

Tell your agent to remember something:

> "Remember that we chose PostgreSQL for storage because it handles hybrid search without a separate vector DB."

Search for it later:

> "What did we decide about the storage layer?"

That's it. 11 tools available. The ones you'll use most:

| Tool | What it does |
|------|-------------|
| `store` | Save a memory with auto-enrichment. Supports `event_at` and `valid_until` for bi-temporal tracking |
| `search` | Find memories (vector + keyword + recency + tags). Temporal filters: `as_of`, `event_after`, `event_before` |
| `recall` | Get full content for specific memory IDs |
| `orient` | Boot a session with rules, recent activity, beliefs, and open work |
| `rules` | Load behavioral guardrails (global or per-project) |
| `beliefs` | Durable epistemic state — crystallize, challenge, retract knowledge with confidence tracking |
| `work_items` | Create, claim, and complete tasks with dependencies and gates |
| `working_memory` | Capture ephemeral thoughts — hypotheses, questions, tensions — with salience decay |
| `projects` | Manage project docs (briefs, PRDs, plans) |
| `code_query` | Structural queries: dependents, impact, callers, callees, dead code, complexity, hotspots |
| `arch_check` | Validate architecture boundary rules against imports |

The rest: `modify`, `insights`, `think`, `status`, `consolidate`, `ingest`.

## What's in the box

**Memory that persists across sessions.** Your agent makes a decision at 2am. Next morning, different session, it finds that decision. That's the core. Bi-temporal tracking separates when something happened (`event_at`) from when you learned it (`created_at`). Memories that go unaccessed decay naturally; important ones are protected. Related memories get consolidated into higher-order insights automatically.

**Beliefs.** Durable epistemic state — knowledge held with confidence. Crystallize hypotheses into beliefs, challenge them with counter-evidence, retract them when wrong. Beliefs surface in session boot alongside rules and memories, giving agents a clear picture of what the organization knows and how confident it is.

**Search that fuses signals.** Vector similarity, recency, access frequency, keyword matching, and tag overlap blended via Reciprocal Rank Fusion. Filter by project, type, or time range. Temporal queries: "what did we know as of Tuesday?" via `as_of`, "what happened last week?" via `event_after`/`event_before`.

**Knowledge graph.** Entities and facts get extracted into a Neo4j graph that connects memories through shared people, places, projects, and concepts. Optional, but powerful when you're working across domains.

**Thinking sequences.** Structured deliberation — start with a goal, add thoughts (observations, hypotheses, analysis, alternatives), conclude. Both humans and agents contribute. The exploration itself becomes searchable memory.

**Work management.** Hierarchical work items with dependency tracking, gates that pause for human decisions, and activity logging. Experimental — evolving as we learn what works.

**Web dashboard.** Browse memories with OKLCH-colored toggle filters, score gradient bars, and shareable URL state. Explore the knowledge graph and entity relationships. View analytics, manage work items. Port 3000.

<p align="center">
  <img src="images/cairn-dashboard.jpg" alt="Cairn dashboard with memory growth and token usage" width="700">
  <br>
  <sub>Memory growth by type, token usage tracking, and the full nav.</sub>
</p>

**Code intelligence.** A standalone worker indexes codebases with tree-sitter (30 languages) and builds a code graph in Neo4j. The server queries the graph without ever touching source files. Ask structural questions — "what depends on this file?", "who calls this function?", "what's the blast radius?" — and get answers from the code graph. Call graph extraction, cyclomatic complexity, dead code detection. Enforce architecture boundaries with YAML rules. Works across projects.

<details>
<summary>Supported languages (30)</summary>

| Category | Languages |
|---|---|
| Systems | C, C++, Rust, Go, Zig |
| JVM | Java, Scala, Kotlin, Groovy |
| .NET | C# |
| Scripting | Python, Ruby, PHP, Lua, Bash |
| Web | TypeScript/TSX, HTML, CSS |
| Apple | Swift, Objective-C |
| ML/Scientific | OCaml, MATLAB |
| Config & Data | JSON, YAML, TOML, HCL (Terraform), Dockerfile, Makefile, SQL, Markdown |

</details>

**Multi-user authentication and RBAC.** Off by default, zero to enterprise in one command. `./scripts/setup.sh` includes auth configuration, or run `./scripts/setup-auth.sh` standalone. Auth mode selection (none / local JWT / OIDC SSO), JWT secret generation, OIDC provider validation. Personal Access Tokens for machine clients, stdio identity for MCP. Three roles, project-level scoping, first-user-becomes-admin. Groups with OIDC sync. See the **[Authentication Guide](docs/authentication.md)**.

**Disaster recovery.** Cron-friendly scripts for PostgreSQL dump and Neo4j graph export with configurable retention. Tested restore procedures with migration safety checks. See the **[Backup Guide](docs/backup.md)**.

## Do I need an LLM?

No. Store, search, recall, and rules work without one. You lose auto-enrichment (summaries, tags, importance scoring), knowledge extraction, and thinking.

If you want enrichment:

| Backend | Setup |
|---------|-------|
| **Ollama** (default) | Install [Ollama](https://ollama.com), pull a model. Cairn connects to `host.docker.internal:11434`. |
| **AWS Bedrock** | Set `CAIRN_LLM_BACKEND=bedrock`, export AWS creds. |
| **Google Gemini** | Set `CAIRN_LLM_BACKEND=gemini`, add `CAIRN_GEMINI_API_KEY`. Free tier available. |
| **OpenAI-compatible** | Set `CAIRN_LLM_BACKEND=openai`, add key. Works with OpenAI, Groq, Together, LM Studio, vLLM. |

## Configuration

All via environment variables. The ones that matter:

| Variable | Default | What it does |
|----------|---------|-------------|
| `CAIRN_PROFILE` | *(empty)* | Preset: `vector`, `enriched`, `knowledge`, `enterprise`. Sets capability defaults. |
| `CAIRN_LLM_BACKEND` | `ollama` | LLM provider: `ollama`, `bedrock`, `gemini`, `openai` |
| `CAIRN_DB_PASS` | `cairn-dev-password` | Database password. Change this for anything beyond local. |
| `CAIRN_AUTH_ENABLED` | `false` | Multi-user authentication (JWT, PATs, OIDC/SSO) |
| `CAIRN_AUTH_JWT_SECRET` | *(empty)* | JWT signing secret (required when auth enabled) |
| `CAIRN_OIDC_ENABLED` | `false` | OIDC/SSO integration (any OIDC-compliant provider) |
| `CAIRN_MCP_OAUTH_ENABLED` | `false` | OAuth2 Authorization Server for remote MCP clients (Claude.ai, mobile) |
| `CAIRN_GRAPH_BACKEND` | *(disabled)* | Set to `neo4j` to enable knowledge graph |
| `CAIRN_KNOWLEDGE_EXTRACTION` | `false` | Entity/statement extraction on store |
| `CAIRN_EMBEDDING_BACKEND` | `local` | `local` (MiniLM, 384-dim) or `bedrock` (Titan V2, 1024-dim) |
| `CAIRN_INGEST_DIR` | `/data/ingest` | Staging directory for file-path ingestion of large documents |
| `CAIRN_CODE_DIR` | `/data/code` | Root directory for code intelligence indexing (mount codebases here) |

Full reference is in [docker-compose.yml](docker-compose.yml). Every variable has a sensible default.

## Authentication

Off by default. The fastest way to enable it is through the setup wizard:

```bash
./scripts/setup.sh          # includes auth as step 2
./scripts/setup-auth.sh     # or run auth setup standalone
```

Three modes — no auth, local JWT, or OIDC/SSO. Generates secrets, validates
your identity provider's discovery endpoint, writes `.env`. Provider-specific
URL hints for Authentik, Keycloak, Auth0, Okta, and Azure AD. Both scripts
support `--dry-run` and `--non-interactive` for CI.

First user to register becomes admin. Role-based access control enforces
permissions across REST API, MCP HTTP, and the web UI. Personal Access Tokens
for machine clients, groups with OIDC sync.

See the **[Authentication Guide](docs/authentication.md)** for the full reference
covering all auth modes, OIDC provider configuration, and MCP client examples.

> **Security note:** Cairn's auth system is functional and production-tested but
> has not been independently audited. For network-exposed deployments, add TLS
> termination and network-level access controls.

## Remote MCP Access (Claude.ai, Mobile)

Connect Cairn to Claude.ai, the Claude mobile app, or any OAuth2-capable MCP client. Cairn acts as an OAuth2 Authorization Server, delegating user authentication to your existing OIDC identity provider.

**Prerequisites:** Auth enabled (`CAIRN_AUTH_ENABLED=true`), OIDC configured (`CAIRN_OIDC_ENABLED=true`), and a public URL set (`CAIRN_PUBLIC_URL`).

**Enable it:**

```bash
CAIRN_MCP_OAUTH_ENABLED=true
```

**Connect from Claude.ai:**

1. Go to Claude.ai Settings > Integrations > Add custom MCP
2. Enter your Cairn URL: `https://your-cairn-domain.com/mcp`
3. Claude.ai discovers the OAuth2 endpoints automatically
4. You'll be redirected to your identity provider to log in
5. After login, Claude.ai has full access to your Cairn MCP tools

The OAuth2 flow uses Authorization Code + PKCE with Dynamic Client Registration (RFC 7591). If your identity provider supports SSO sessions, the auth redirect is invisible after the first login.

See the **[Remote MCP Guide](docs/remote-mcp.md)** for reverse proxy configuration, security hardening, and troubleshooting.

## Code Intelligence

Code intelligence runs as a **standalone worker** that indexes source code and writes to Neo4j. The cairn server queries the graph but never touches source files directly. This separation means indexing doesn't block the event loop and the worker can run on the machine where code lives.

**Requirements:** Neo4j (the `cairn-graph` service in docker-compose) must be running.

### Quick start

```bash
# Index a single project (one-shot, no watching)
python -m cairn.code \
  --watch /path/to/your/repo:your-project \
  --neo4j-uri bolt://localhost:7687 \
  --cairn-url http://localhost:8000 \
  --no-watch

# Index and watch for changes (long-running)
python -m cairn.code \
  --watch /home/user/working/myproject:myproject \
  --watch /home/user/working/other:other \
  --neo4j-uri bolt://my-server:7687
```

### Environment variables

| Variable | Default | What it does |
|----------|---------|-------------|
| `CAIRN_NEO4J_URI` | `bolt://localhost:7687` | Neo4j bolt URI |
| `CAIRN_NEO4J_USER` | `neo4j` | Neo4j username |
| `CAIRN_NEO4J_PASSWORD` | `cairn-dev-password` | Neo4j password |
| `CAIRN_API_URL` | `http://localhost:8000` | Cairn server URL (for project ID resolution) |
| `CAIRN_API_KEY` | *(empty)* | API key if cairn auth is enabled |
| `CAIRN_CODE_PROJECTS` | *(empty)* | Comma-separated `project=path` pairs (alternative to `--watch`) |
| `CAIRN_CODE_WATCH` | `true` | Enable filesystem watching after initial index |
| `CAIRN_CODE_FORCE` | `false` | Force re-index even if content hash unchanged |

### Docker / remote codebases

Mount source code into the cairn container and set `CAIRN_CODE_DIR`:

```yaml
# docker-compose.yml
volumes:
  - /path/to/code:/data/code:ro   # read-only mount
environment:
  CAIRN_CODE_DIR: /data/code
```

Or run the worker on the code host and point it at your cairn + Neo4j instances:

```bash
CAIRN_NEO4J_URI=bolt://cairn-host:7687 \
CAIRN_API_URL=http://cairn-host:8000 \
CAIRN_CODE_PROJECTS="myproject=/home/user/code/myproject" \
python -m cairn.code
```

### What gets indexed

- **Symbols:** functions, classes, methods, interfaces, enums, React components/hooks
- **Relationships:** `IMPORTS` (file-level), `CALLS` (function-level), `CONTAINS` (parent-child)
- **Metadata:** signatures, docstrings, cyclomatic complexity, line numbers, content hashes
- **Languages:** Python, TypeScript/TSX, and 28 more (C, Rust, Go, Java, Ruby, etc.)

### Query examples (via `code_query` MCP tool)

| Action | What it does |
|--------|-------------|
| `dependents` | Files that import the target |
| `dependencies` | Files the target imports |
| `callers` | Functions that call the target |
| `callees` | Functions the target calls |
| `call_chain` | Trace call paths between two functions |
| `dead_code` | Functions with zero callers |
| `complexity` | Rank functions by cyclomatic complexity |
| `impact` | Blast radius — transitive dependents |
| `hotspots` | PageRank — structurally important files |
| `search` | Fulltext search over symbol names and docstrings |

## Architecture

```
MCP clients (Claude Code, Cursor, PiClaw)    REST clients (web UI, scripts)
        |                                            |
        | MCP (stdio or HTTP)                        | REST API
        |                                            |
+-------v--------------------------------------------v--------+
|  cairn.server (MCP tools)     cairn.api (FastAPI endpoints) |
|                                                             |
|  core: memory, search, enrichment, extraction, clustering   |
|        working memory, beliefs, thinking, work items        |
|                                                             |
|  embedding: local (MiniLM) or Bedrock (Titan V2)            |
|  llm: Ollama, Bedrock, Gemini, OpenAI-compatible            |
+------+----------------------------------------------+------++
       |                                              |       |
       v                                              v       |
  PostgreSQL 16 + pgvector                    Neo4j 5 <-------+
                                             (optional)       |
                                                ^             |
  code worker (python -m cairn.code)            |             |
  tree-sitter parsing, call graph      --------+             |
  watches filesystem for changes                             |
```

## Benchmark

Tested against [LoCoMo](https://github.com/snap-stanford/locomo), a long-conversation memory benchmark with 1,986 questions across five categories.

| System | Score | LLM |
|--------|-------|-----|
| **Cairn** | **81.6%** | Llama-3.3-70B |
| Human baseline | 87.9% | — |
| Letta/MemGPT | 74.0% | GPT-4o-mini |
| Mem0 | 66.9% | GPT-4o |

Test configuration: Titan V2 embeddings (Bedrock, 1024-dim), episodic ingestion (raw turns + two-pass fact extraction), Search V2 with graph-primary retrieval, type routing, cross-encoder reranking, LLM-as-judge evaluation. Full results and methodology in [`eval/`](eval/).

## Development

```bash
git clone https://github.com/jasondostal/cairn-mcp.git
cd cairn-mcp
cp .env.example .env
docker compose up -d --build
```

## Status

Cairn is under active development. It's a real system used daily in production, and it's evolving as I learn what actually works for agent memory. Migrations handle schema changes. If something breaks, [open an issue](https://github.com/jasondostal/cairn-mcp/issues).

## License

[GNU General Public License v3.0](LICENSE)
