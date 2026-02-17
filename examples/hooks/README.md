# Cairn Session Hooks

Automatic session capture using lifecycle hooks. Works with Claude Code, Cursor, Windsurf, and Cline.

## What it does

Three core scripts handle the universal contract. IDE-specific adapters translate field names.

| Core script | When | What happens |
|------|------|-------------|
| `session-start.sh` | Session begins | Publishes `session_start` event, outputs session context |
| `log-event.sh` | After every tool use | Publishes `tool_use` event (fire-and-forget) |
| `session-end.sh` | Session ends | Publishes `session_end` event, closes the session |

**Event bus architecture:** Each hook POSTs a single event directly to `POST /api/events`. No local files, no batching, no offset tracking. The server auto-creates session records on `session_start` events and auto-closes them on `session_end` events. Events are available immediately via `GET /api/events` or real-time via `GET /api/events/stream` (SSE).

## IDE Hook Capabilities

| IDE | Session start | Tool capture | Session end | Auto-session |
|-----|:---:|:---:|:---:|:---:|
| Claude Code | yes | yes | yes | yes |
| Cursor | yes | yes | yes | yes |
| Cline | yes | yes | yes | yes |
| Windsurf | auto* | yes | manual | partial |
| Continue | — | — | — | — |

\*Windsurf: session initializes on first tool use (no session-start hook). No session-end hook — sessions remain open until manually closed.

## Quick Start

### Automatic setup (all IDEs)

```bash
/path/to/cairn/scripts/setup.sh
```

The setup script detects your installed IDEs, configures MCP connections, and installs the appropriate hook adapters. Use `--dry-run` to preview changes.

### Manual setup by IDE

<details>
<summary><strong>Claude Code</strong></summary>

Add to `.claude/settings.local.json` (project) or `~/.claude/settings.json` (global):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "CAIRN_URL=http://YOUR_CAIRN_HOST:8000 /absolute/path/to/cairn/examples/hooks/session-start.sh",
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
            "command": "CAIRN_URL=http://YOUR_CAIRN_HOST:8000 /absolute/path/to/cairn/examples/hooks/log-event.sh",
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
            "command": "CAIRN_URL=http://YOUR_CAIRN_HOST:8000 /absolute/path/to/cairn/examples/hooks/session-end.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

**Important:** Set `CAIRN_URL` on all three hook commands, not just session-start. Each hook runs as a separate process with no shared environment.

Claude Code calls the core scripts directly — no adapter needed.

</details>

<details>
<summary><strong>Cursor</strong></summary>

Cursor's hook system uses different field names (`sessionId`, `workspaceFolder`, `toolName`). The adapters in `adapters/cursor/` translate these to Cairn's contract.

Add to `.cursor/hooks.json`:

```json
{
  "hooks": {
    "session-start": {
      "command": "CAIRN_URL=http://YOUR_CAIRN_HOST:8000 /absolute/path/to/cairn/examples/hooks/adapters/cursor/session-start.sh",
      "timeout": 15
    },
    "after-mcp-execution": {
      "command": "CAIRN_URL=http://YOUR_CAIRN_HOST:8000 /absolute/path/to/cairn/examples/hooks/adapters/cursor/after-mcp-execution.sh",
      "timeout": 5
    },
    "session-end": {
      "command": "CAIRN_URL=http://YOUR_CAIRN_HOST:8000 /absolute/path/to/cairn/examples/hooks/adapters/cursor/session-end.sh",
      "timeout": 30
    }
  }
}
```

**How it works:** Each adapter reads Cursor's JSON from stdin, remaps field names with defensive fallbacks (`jq` `//` operator), and pipes to the corresponding core script.

</details>

<details>
<summary><strong>Windsurf</strong></summary>

Windsurf only provides a `post_mcp_tool_use` hook — no session start or end. The adapter handles this by auto-initializing the session on the first tool use.

Add to your Windsurf hooks config (`.windsurf/hooks.json` or `~/.codeium/windsurf/hooks.json`):

```json
{
  "hooks": {
    "post-mcp-tool-use": {
      "command": "CAIRN_URL=http://YOUR_CAIRN_HOST:8000 /absolute/path/to/cairn/examples/hooks/adapters/windsurf/post-mcp-tool-use.sh",
      "timeout": 10
    }
  }
}
```

**How it works:** On each tool call, the adapter checks for a temp marker file (`/tmp/cairn-session-{id}`). If absent, it runs `session-start.sh` first (transparent init), then forwards to `log-event.sh`.

**Limitation:** No session-end hook. Sessions will remain open until manually closed:

```bash
curl -X POST http://localhost:8000/api/sessions/YOUR_SESSION_NAME/close
```

</details>

<details>
<summary><strong>Cline (VS Code)</strong></summary>

Cline hooks must return JSON on stdout. The adapters in `adapters/cline/` handle this — they run the core scripts, capture output, and wrap it in Cline's expected format.

Cline uses `taskId` (not `session_id`) and `workingDirectory` (not `cwd`). The adapters translate these automatically.

Install the hook scripts to Cline's hooks directory:

```bash
# Copy adapters
cp /path/to/cairn/examples/hooks/adapters/cline/* ~/.cline/hooks/
chmod +x ~/.cline/hooks/TaskStart ~/.cline/hooks/PostToolUse ~/.cline/hooks/TaskCancel
```

| Cline hook | Cairn adapter | Core script |
|-----------|--------------|-------------|
| `TaskStart` | `adapters/cline/TaskStart` | `session-start.sh` → wraps stdout in `{contextModification}` |
| `PostToolUse` | `adapters/cline/PostToolUse` | `log-event.sh` → returns `{cancel: false}` |
| `TaskCancel` | `adapters/cline/TaskCancel` | `session-end.sh` → returns `{cancel: false}` |

</details>

<details>
<summary><strong>Continue</strong></summary>

Continue does not currently support lifecycle hooks. Cairn still works — agents store memories via MCP tools, and `orient()` provides session boot context.

</details>

## Core Script Contract

The core scripts are IDE-agnostic. Any agent with lifecycle hooks can use them directly or via adapters.

| Event | Stdin JSON | Script | Stdout |
|-------|-----------|--------|--------|
| Session start | `{"session_id": "...", "cwd": "..."}` | `session-start.sh` | Cairn context (text) |
| Tool use | `{"session_id": "...", "tool_name": "...", "tool_input": {...}, "tool_response": "..."}` | `log-event.sh` | (none) |
| Session end | `{"session_id": "...", "reason": "..."}` | `session-end.sh` | (none, logs to stderr) |

Requirements:
- A unique `session_id` per session (passed in stdin JSON)
- `jq` and `curl` installed on the system
- `CAIRN_URL` environment variable pointing to your Cairn instance

## Adapter Architecture

```
IDE stdin JSON                Core scripts
     |                            |
     v                            v
 adapters/cursor/*.sh    ──→  session-start.sh
 adapters/windsurf/*.sh  ──→  log-event.sh
 adapters/cline/*        ──→  session-end.sh
     |                            |
     | Translate field names      | Universal contract:
     | Add response wrappers      |   {session_id, tool_name,
     | Handle IDE quirks          |    tool_input, tool_response}
     v                            v
 IDE-specific JSON out       POST /api/events
```

Each adapter is a thin wrapper (~20 lines) that:
1. Reads IDE-specific stdin JSON
2. Translates field names to Cairn's contract using `jq` with defensive fallbacks
3. Pipes to the core script
4. Wraps response if needed (Cline requires JSON on stdout)

**Caveat:** The exact stdin JSON field names for Cursor, Windsurf, and Cline are based on documentation research and may vary across versions. Adapters use defensive fallbacks (e.g., `.sessionId // .session_id // "unknown"`) to handle variations. If you encounter field name mismatches, please report them.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_URL` | `http://localhost:8000` | Cairn API base URL |
| `CAIRN_API_KEY` | (none) | API key for authenticated Cairn instances |
| `CAIRN_PROJECT` | `$(basename $CWD)` | Project name for this session |
| `CAIRN_AGENT_TYPE` | `interactive` | Agent type metadata (e.g., `interactive`, `ci`, `dispatch`) |
| `CAIRN_PARENT_SESSION` | (none) | Parent session name for sub-agent tracking |
| `CAIRN_SESSION_NAME` | (auto-derived) | Override session name (normally auto-derived from date + session ID) |

## How it works

```
Session start (hook or adapter)
    |
    +-- POST /api/events {event_type: "session_start", ...}
    |   Server auto-creates session record in sessions table (upsert)
    |
    +-- Output: session_name, active_project
    |   (Agent reads this as session context)
    |
    |   +----------------------------------------------+
    +---| Tool use hook (every tool)                    |
    |   | POST /api/events {event_type: "tool_use",     |
    |   |   tool_name, payload: {tool_input, response}} |
    |   | Fire-and-forget, backgrounded                 |
    |   +----------------------------------------------+
    |         ... repeat ...
    |
    |   (Events available immediately via REST or SSE)
    |
Session end (hook or adapter)
    |
    +-- POST /api/events {event_type: "session_end", ...}
    |   Server auto-closes session (sets closed_at)
    |
    +-- POST /api/sessions/{name}/close (belt-and-suspenders)
```

**Key design:** No LLM in the hot path. Events are raw INSERT + Postgres NOTIFY. Zero cost per event, sub-millisecond latency. Analysis happens asynchronously via MCP tools (search, synthesize, orient).

## Verification

### During a session

```bash
# Events should appear for the current session:
curl -s http://localhost:8000/api/events?session_name=YOUR_SESSION | jq '.count'

# Real-time streaming (SSE):
curl -N http://localhost:8000/api/events/stream?session_name=YOUR_SESSION
```

### After a session

```bash
# Session should show as closed:
curl -s http://localhost:8000/api/sessions | jq '.items[0]'

# All events for the session:
curl -s "http://localhost:8000/api/events?session_name=YOUR_SESSION&limit=100" | jq '.items | length'
```

## Troubleshooting

### Sessions show as active indefinitely

The session-end hook may not have fired. Manually close:

```bash
curl -X POST http://localhost:8000/api/sessions/YOUR_SESSION_NAME/close
```

### CAIRN_URL is wrong

If hooks can't reach Cairn, events are silently dropped (fire-and-forget design).

```bash
# Test connectivity:
curl -s http://YOUR_CAIRN_HOST:8000/api/status | jq '.status'
# Should return: "healthy"
```

Common issues:
- Using `localhost` when Cairn runs on a different host (e.g., in a VM or container)
- Port mismatch (default is 8000)
- Firewall blocking the port
- Missing `CAIRN_URL` prefix on hook commands (each hook is a separate process)

### jq not installed

The hooks require `jq` for JSON processing. Install it:

```bash
# macOS
brew install jq

# Ubuntu/Debian
sudo apt-get install jq

# Alpine (in Docker)
apk add jq
```

### Hook timeout errors

If session-start or session-end hooks are timing out:
- Increase the `timeout` value in your hook config (session-start: 15s, session-end: 30s)
- Check if Cairn is slow to respond — the event bus is lightweight, but network latency can add up

## Customization

- **Filter noisy tools:** Add a matcher to the tool-use hook config (e.g., `"matcher": "Bash|Edit|Write"` for Claude Code)
- **Skip event capture:** Remove the tool-use hook entirely — memories stored via MCP still work, just without the event stream
- **Different project per directory:** Set `CAIRN_PROJECT` in your project-level hook config
