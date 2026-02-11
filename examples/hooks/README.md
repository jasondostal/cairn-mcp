# Cairn Session Hooks

Automatic session capture using lifecycle hooks. Works with Claude Code, Cursor, Windsurf, and Cline.

## What it does

Three core scripts handle the universal contract. IDE-specific adapters translate field names.

| Core script | When | What happens |
|------|------|-------------|
| `session-start.sh` | Session begins | Loads recent cairns as context, creates event log |
| `log-event.sh` | After every tool use | Captures full event, ships batches of 25 incrementally |
| `session-end.sh` | Session ends | Ships remaining events, sets a cairn via REST API |

**Pipeline v2:** Events are captured with full fidelity (`tool_input` + `tool_response`), shipped in batches of 25 to `POST /api/events/ingest` during the session, digested by the server's DigestWorker into rolling LLM summaries, and crystallized into cairn narratives at session end. An `.offset` sidecar file tracks what's been shipped.

## IDE Hook Capabilities

| IDE | Session start | Tool capture | Session end | Auto-cairn |
|-----|:---:|:---:|:---:|:---:|
| Claude Code | yes | yes | yes | yes |
| Cursor | yes | yes | yes | yes |
| Cline | yes | yes | yes | yes |
| Windsurf | auto* | yes | manual | manual |
| Continue | — | — | — | — |

\*Windsurf: session initializes on first tool use (no session-start hook). No session-end hook — the agent calls `cairns(action="set")` directly.

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
            "command": "/absolute/path/to/cairn/examples/hooks/log-event.sh",
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

**How it works:** On each tool call, the adapter checks if an event log exists for the session. If not, it runs `session-start.sh` first (transparent init), then forwards to `log-event.sh`.

**Limitation:** No session-end hook. To crystallize a cairn, the agent must call `cairns(action="set")` directly (Tier 2), or you can manually run:

```bash
echo '{"session_id":"YOUR_SESSION_ID"}' | CAIRN_URL=http://localhost:8000 /path/to/cairn/examples/hooks/session-end.sh
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

Continue does not currently support lifecycle hooks. Cairn still works at Tier 1 (organic) and Tier 2 (agent calls `cairns(action="set")` directly).

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
 IDE-specific JSON out       Cairn event pipeline
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
| `CAIRN_PROJECT` | `$(basename $CWD)` | Project name for this session's cairn |
| `CAIRN_EVENT_DIR` | `~/.cairn/events` | Directory for session event logs (JSONL files) |
| `CAIRN_EVENT_BATCH_SIZE` | `25` | Events per batch before shipping to server |

## How it works

```
Session start (hook or adapter)
    |
    +-- GET /api/cairns?limit=5
    |   Returns recent cairns (all projects) for context
    |
    +-- Output: session_name, active_project, recent cairn summaries
    |   (Agent reads this as session context)
    |
    +-- Create ~/.cairn/events/cairn-events-{session_id}.jsonl
    +-- Create .offset sidecar (starts at 0)
    +-- Write session_start event with session_name
         |
         |  +--------------------------------------------+
         +--| Tool use hook (every tool)                  |
         |  | Capture: tool_name, tool_input, tool_response|
         |  | Append to JSONL event log                    |
         |  | Every 25 events → background ship batch to   |
         |  |   POST /api/events/ingest                    |
         |  | .offset tracks what's been shipped           |
         |  +--------------------------------------------+
         |         ... repeat ...
         |
         |  (Server-side: DigestWorker processes batches
         |   into 2-4 sentence LLM summaries as they arrive)
         |
Session end (hook or adapter or agent)
    |
    +-- Ship any remaining unshipped events as final batch
    +-- POST /api/cairns {project, session_name}
    |   (No events payload — server pulls digests from session_events)
    |   |
    |   +-- Cairn already exists (agent set it via MCP)?
    |   |   -> Merge: re-synthesize narrative from digests
    |   |
    |   +-- No cairn yet?
    |       -> Create cairn with narrative from digests + stones
    |
    +-- Archive event log + offset to ~/.cairn/events/archive/
```

**Key design:** The agent (via MCP tool) and the hook (via REST POST) can both set a cairn for the same session. Whichever arrives first creates it; the second one merges in whatever the first was missing (events or stones). No race condition, no errors.

## The three tiers

These hooks are **Tier 3** — fully automatic. Cairn works at all three tiers:

- **Tier 1 (Organic):** Agent follows behavioral rules, stores memories with `session_name`, sets cairns manually. No hooks needed.
- **Tier 2 (Tool-assisted):** Agent calls `cairns(action="set")` at session end. One tool call.
- **Tier 3 (Hook-automated):** These scripts + adapters. Zero agent effort. Events captured automatically.

Each tier is additive. If hooks aren't installed, Tier 2 still works. If the agent forgets to set a cairn, Tier 1 memories still exist.

## Verification

### During a session

```bash
# Event log should exist and grow with each tool call:
ls -la ~/.cairn/events/cairn-events-*.jsonl
wc -l ~/.cairn/events/cairn-events-*.jsonl
```

### After a session

```bash
# Event log + offset should be archived (not deleted):
ls ~/.cairn/events/archive/

# Latest cairn should exist with narrative:
curl -s http://localhost:8000/api/cairns?limit=1 | jq '.[] | {id, title, memory_count}'

# Check event batches and digest status:
curl -s "http://localhost:8000/api/events?project=YOUR_PROJECT&session_name=SESSION" | jq '.[] | {batch_number, event_count, digested: (.digest != null)}'
```

### In the web UI

Open the Cairns page. Cairns with digested events will show a richer narrative synthesized from both the pre-digested event summaries and stored memories.

## Troubleshooting

### Cairns exist but narratives are generic

**Possible causes:**
- DigestWorker isn't running (check `docker logs cairn 2>&1 | grep DigestWorker`)
- LLM backend is unavailable (digests require LLM)
- `CAIRN_LLM_EVENT_DIGEST=false` disables digestion — cairn falls back to raw events or stones-only narrative
- Events shipped but not yet digested — DigestWorker processes async, check `GET /api/events` for digest status

### CAIRN_URL is wrong

If hooks can't reach Cairn, you'll see `{"error": "failed to reach cairn"}` in your IDE's debug output.

```bash
# Test connectivity:
curl -s http://YOUR_CAIRN_HOST:8000/api/status | jq '.status'
# Should return: "ok"
```

Common issues:
- Using `localhost` when Cairn runs on a different host (e.g., in a VM or container)
- Port mismatch (default is 8000, not 8002)
- Firewall blocking the port

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

### Permission issues on event directory

```bash
# Ensure the event directory exists and is writable:
mkdir -p ~/.cairn/events/archive
chmod 755 ~/.cairn/events
```

### Hook timeout errors

If session-start or session-end hooks are timing out:
- Increase the `timeout` value in your hook config (session-start: 15s, session-end: 30s)
- Check if Cairn is slow to respond (LLM synthesis can take time)
- For session-end, the narrative synthesis happens server-side — the hook just POSTs and returns

## Customization

- **Adjust batch size:** Set `CAIRN_EVENT_BATCH_SIZE` (default 25). Smaller = more frequent shipping, more digests. Larger = fewer HTTP calls.
- **Filter noisy tools:** Add a matcher to the tool-use hook config (e.g., `"matcher": "Bash|Edit|Write"` for Claude Code)
- **Skip event capture:** Remove the tool-use hook entirely — cairns still work, just without the event stream
- **Different project per directory:** Set `CAIRN_PROJECT` in your project-level hook config
- **Disable digestion:** Set `CAIRN_LLM_EVENT_DIGEST=false` — events still ship and store, but no LLM summaries. Cairn narratives fall back to raw events.
