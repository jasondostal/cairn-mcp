# Cairn Agent Workspace

Dispatch autonomous coding agents from the web UI or from work items. Cairn assembles project context — rules, memories, trail, dispatch briefing — and injects it into an agent session. Two backends supported: Claude Code and OpenCode.

## How it works

```
Work item (or manual task)
    |
    +-- POST /workspace/sessions {project, work_item_id, backend, risk_tier}
    |
    |   Cairn generates a dispatch briefing:
    |     - Work item details + acceptance criteria
    |     - Cascaded constraints from parent items
    |     - Linked memories for context
    |     - Prior gate resolutions (if re-dispatching)
    |
    +-- Agent session starts (Claude Code subprocess or OpenCode HTTP)
    |     - Agent receives briefing as initial prompt
    |     - MCP access to Cairn for orient(), search(), recall()
    |     - Risk tier controls permission boundaries
    |
    +-- Agent works autonomously
    |     - Updates work item status (claim → in_progress → done)
    |     - Heartbeats report progress
    |     - Gates pause for human input when needed
    |
    +-- Session ends
          - Diff available via GET /workspace/sessions/{id}/diff
          - Activity logged to work item feed
```

## Backends

| Backend | How it runs | Best for |
|---------|------------|----------|
| **Claude Code** | Spawns `claude -p` as a subprocess inside the cairn container | Teams already using Claude Code, fine-grained permission control via risk tiers |
| **OpenCode** | HTTP calls to an OpenCode headless server | Multi-model agent pools, custom agents, Bedrock/OpenAI models |

Both can be enabled simultaneously. Choose per-session from the UI or API.

## Quick Start — Claude Code

### 1. Install Claude Code on the host

Follow the [official install guide](https://docs.anthropic.com/en/docs/claude-code). Authenticate:

```bash
claude auth login
```

Verify the CLI works:

```bash
claude --version
which claude  # note this path
```

### 2. Configure docker-compose.override.yml

Create a `docker-compose.override.yml` alongside your `docker-compose.yml`:

```yaml
services:
  cairn:
    environment:
      CAIRN_CLAUDE_CODE_ENABLED: "true"
      CAIRN_CLAUDE_CODE_WORKING_DIR: "/path/to/your/project"
      CAIRN_CLAUDE_CODE_MAX_TURNS: "25"
      CAIRN_CLAUDE_CODE_MAX_BUDGET: "10.00"
      CAIRN_CLAUDE_CODE_MCP_URL: "http://localhost:8000/mcp"
    volumes:
      # Claude Code CLI binary (read-only)
      - /path/to/claude:/usr/local/bin/claude:ro

      # Claude Code auth + config
      # UIDs must match: host user UID should equal container cairn UID (1000)
      - ~/.claude:/home/cairn/.claude

      # Working directory for agent sessions (must be writable)
      - /path/to/your/project:/path/to/your/project
```

### 3. Restart

```bash
docker compose up -d --no-deps cairn
```

### 4. Verify

```bash
curl -s http://localhost:8000/api/workspace/health | jq
# Should show claude_code backend as healthy

curl -s http://localhost:8000/api/workspace/agents | jq
# Should list claude-code-opus and claude-code-sonnet
```

### Volume mounts explained

| Mount | Why | Notes |
|-------|-----|-------|
| `/path/to/claude:/usr/local/bin/claude:ro` | The Claude CLI binary. Mounted read-only — the container just needs to execute it. | Find your path with `which claude` |
| `~/.claude:/home/cairn/.claude` | Auth tokens, MCP config, session history. Claude Code reads this on every invocation. | UID 1000 on both sides. If your host UID differs, adjust container user. |
| Project directory | The working directory where the agent reads/writes code. | Must match `CAIRN_CLAUDE_CODE_WORKING_DIR`. Must be writable. |

### MCP self-service

When `CAIRN_CLAUDE_CODE_MCP_URL` is set, Cairn generates a temporary MCP config file and passes it to the Claude CLI via `--mcp-config`. This gives agents full MCP tool access to Cairn — they can call `orient()`, `search()`, `recall()`, update work items, and store memories during execution.

The config uses `"type": "http"` transport (not `"type": "url"` — the latter silently fails in Claude CLI ≤2.1.47).

## Quick Start — OpenCode

### 1. Install and run OpenCode

Follow the [OpenCode docs](https://github.com/opencode-ai/opencode). Start the headless server:

```bash
OPENCODE_SERVER_PASSWORD=your-secure-password opencode server
```

### 2. Configure environment

Add to your `.env` or `docker-compose.override.yml`:

```yaml
services:
  cairn:
    environment:
      CAIRN_OPENCODE_URL: "http://your-opencode-host:8080"
      CAIRN_OPENCODE_PASSWORD: "your-secure-password"
      CAIRN_OPENCODE_DEFAULT_AGENT: "cairn-build"
```

### 3. Restart and verify

```bash
docker compose up -d --no-deps cairn
curl -s http://localhost:8000/api/workspace/health | jq
```

### OpenCode MCP integration

For full context access, register Cairn as an MCP server in your OpenCode config:

```json
{
  "mcpServers": {
    "cairn": {
      "type": "http",
      "url": "http://your-cairn-host:8000/mcp"
    }
  }
}
```

## Configuration Reference

### Claude Code

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_CLAUDE_CODE_ENABLED` | `false` | Enable the Claude Code backend |
| `CAIRN_CLAUDE_CODE_WORKING_DIR` | *(empty)* | Working directory for agent subprocess |
| `CAIRN_CLAUDE_CODE_MAX_TURNS` | `25` | Max conversation turns per session |
| `CAIRN_CLAUDE_CODE_MAX_BUDGET` | `10.0` | Max USD spend per session (0 = unlimited) |
| `CAIRN_CLAUDE_CODE_MCP_URL` | *(empty)* | Cairn MCP endpoint for agent self-service |

### OpenCode

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_OPENCODE_URL` | *(empty)* | OpenCode headless server URL |
| `CAIRN_OPENCODE_PASSWORD` | *(empty)* | Server password |
| `CAIRN_OPENCODE_DEFAULT_AGENT` | `cairn-build` | Default agent for new sessions |

### General

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_WORKSPACE_BACKEND` | `opencode` | Default backend when not specified per-session |

## Risk Tiers

Risk tiers control what agents are allowed to do. They map to Claude Code's permission system and affect dispatch briefing language.

| Tier | Label | What the agent can do | Use case |
|------|-------|-----------------------|----------|
| **0** | patrol | Full autonomy — no permission restrictions | Trusted automation, internal tooling, test suites |
| **1** | caution | Read, edit, write files + bash + MCP tools | General feature development, refactoring |
| **2** | action | Read files + bash + MCP tools (no edit/write) | Analysis, investigation, read-heavy research |
| **3** | critical | Read, glob, grep + search/recall only (no bash, no edits) | Sensitive reviews, production assessment |

Set risk tier at dispatch time:

```bash
# Via API
curl -X POST http://localhost:8000/api/workspace/sessions \
  -H 'Content-Type: application/json' \
  -d '{"project": "my-project", "work_item_id": 42, "backend": "claude_code", "risk_tier": 1}'
```

Or select from the UI when creating a session.

Risk tiers only affect the Claude Code backend (via `--allowedTools`). OpenCode sessions use the agent's own permission model.

## Dispatch Briefing

When you dispatch from a work item (`work_item_id` parameter), Cairn assembles a structured briefing:

```
[DISPATCH BRIEFING]
You are assigned to work item **wi-xxxx**: <title>
Risk tier: 1 (caution)

## Description
<work item description>

## Acceptance Criteria
<definition of done>

## Parent Context
epic wi-0040: Semantic code indexing → **wi-0040.1** (you are here)

## Constraints
- **language**: python, typescript
- **scope**: no breaking changes

## Linked Context
- [decision] Chose tree-sitter over regex for AST parsing
- [research] Voyage-3-code embeddings benchmark results

## Instructions
- Update this work item's status as you progress
- Use heartbeat to report progress
- Set a gate if you need human input before proceeding
- You may call orient() or search() via MCP for additional project context
```

### Gate continuity

When a work item is re-dispatched after a human resolves a gate, the briefing includes the gate history:

```
## Prior Gate (Resolved)
**Question asked:** Should we support Ruby in the initial release?
  - Yes, include Ruby parser
  - No, defer to v2
**Human answered:** No, defer to v2
Do NOT re-ask this question. Proceed with the chosen option.
```

This preserves decision continuity across dispatch cycles — agents don't re-litigate resolved questions.

## API Reference

### Session lifecycle

| Endpoint | Description |
|----------|-------------|
| `POST /workspace/sessions` | Create a session (accepts `project`, `work_item_id`, `backend`, `risk_tier`, `model`) |
| `GET /workspace/sessions` | List sessions (filter by `?project=`) |
| `GET /workspace/sessions/{id}` | Session detail |
| `POST /workspace/sessions/{id}/message` | Send a message to the agent |
| `POST /workspace/sessions/{id}/abort` | Abort a running session |
| `DELETE /workspace/sessions/{id}` | Delete a session |

### Observability

| Endpoint | Description |
|----------|-------------|
| `GET /workspace/sessions/{id}/messages` | Message history |
| `GET /workspace/sessions/{id}/diff` | File diffs from the session |
| `GET /workspace/health` | Backend health status |
| `GET /workspace/backends` | List backends with capabilities |
| `GET /workspace/agents` | Available agents across all backends |

## Troubleshooting

### Claude Code: "claude: not found"

The CLI binary isn't accessible inside the container. Check:

```bash
# Is it mounted?
docker exec cairn ls -la /usr/local/bin/claude

# Can it execute?
docker exec cairn claude --version
```

Common issues:
- Wrong path in volume mount (check `which claude` on host)
- Binary is a shell wrapper, not the actual ELF — mount the real binary
- Missing `libc` compatibility (unlikely with `node:20-slim` base)

### Claude Code: "Authentication required"

The `.claude` directory isn't mounted or has wrong permissions:

```bash
# Check mount
docker exec cairn ls -la /home/cairn/.claude/

# Check UID match
docker exec cairn id
# Should be uid=1000(cairn)
ls -la ~/.claude/
# Host UID should match
```

### OpenCode: connection refused

```bash
# Is the server running?
curl -s http://your-opencode-host:8080/health

# Is the password correct?
curl -s -u opencode:your-password http://your-opencode-host:8080/agent
```

### Backend not showing in UI

Both backends must pass health checks to appear. Check:

```bash
curl -s http://localhost:8000/api/workspace/health | jq
```

If a backend shows as unhealthy, check its specific connectivity (see above).

### "No workspace backends configured"

Neither `CAIRN_OPENCODE_URL` nor `CAIRN_CLAUDE_CODE_ENABLED=true` is set. At least one backend must be configured for the workspace feature to activate.
