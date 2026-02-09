# Cairn Session Hooks

Automatic session capture using lifecycle hooks. Three scripts, zero manual effort.

## What it does

| Hook | When | What happens |
|------|------|-------------|
| `session-start.sh` | Session begins | Loads recent cairns as context, creates event log |
| `log-event.sh` | After every tool use | Captures full event, ships batches of 25 incrementally |
| `session-end.sh` | Session ends | Ships remaining events, sets a cairn via REST API |

**Pipeline v2:** Events are captured with full fidelity (`tool_input` + `tool_response`), shipped in batches of 25 to `POST /api/events/ingest` during the session, digested by the server's DigestWorker into rolling LLM summaries, and crystallized into cairn narratives at session end. An `.offset` sidecar file tracks what's been shipped.

## Quick Start (Claude Code)

### 1. Run the setup script

```bash
/path/to/cairn/scripts/setup-hooks.sh
```

This checks dependencies, tests connectivity, and generates the settings.json snippet for you.

### 2. Or manual setup

Add this to your `.claude/settings.local.json` (project-level) or `~/.claude/settings.json` (global):

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

Replace `/absolute/path/to/cairn` with wherever you cloned the repo. Replace `YOUR_CAIRN_HOST` with your Cairn server address (or `localhost` if running locally).

### 3. Verify it works

Start a new Claude Code session and do some work. Then check:

```bash
# During a session — events should be accumulating:
ls ~/.cairn/events/cairn-events-*.jsonl
cat ~/.cairn/events/cairn-events-*.jsonl.offset  # shows shipped count

# After a session — cairn should exist, event batches should be digested:
curl -s http://YOUR_CAIRN_HOST:8000/api/cairns?limit=1 | jq '.[0] | {title, memory_count}'
curl -s "http://YOUR_CAIRN_HOST:8000/api/events?project=YOUR_PROJECT&session_name=SESSION" | jq '.[] | {batch_number, event_count, digested: (.digest != null)}'
```

## Quick Start (Other MCP Clients)

The hooks are agent-agnostic bash scripts. Any AI coding agent with lifecycle hooks can use them.

**Contract:** Each script reads JSON from stdin and writes to stdout/stderr.

| Event | Stdin JSON | Script | What it does |
|-------|-----------|--------|-------------|
| Session start | `{"session_id": "...", "cwd": "..."}` | `session-start.sh` | Outputs cairn context to stdout, creates event log |
| Tool use | `{"session_id": "...", "tool_name": "...", "tool_input": {...}, "tool_response": "..."}` | `log-event.sh` | Captures event, ships batch of 25 via `POST /api/events/ingest` |
| Session end | `{"session_id": "...", "reason": "..."}` | `session-end.sh` | Ships remaining events, sets cairn via `POST /api/cairns` |

Wire these into your agent's lifecycle hooks. The only requirements are:
- A unique `session_id` per session (passed in stdin JSON)
- `jq` and `curl` installed on the system
- `CAIRN_URL` environment variable pointing to your Cairn instance

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_URL` | `http://localhost:8000` | Cairn API base URL |
| `CAIRN_PROJECT` | `$(basename $CWD)` | Project name for this session's cairn |
| `CAIRN_EVENT_DIR` | `~/.cairn/events` | Directory for session event logs (JSONL files) |
| `CAIRN_EVENT_BATCH_SIZE` | `25` | Events per batch before shipping to server |

## How it works

```
SessionStart hook
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
         +--| PostToolUse hook (every tool)               |
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
SessionEnd hook
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
- **Tier 3 (Hook-automated):** These scripts. Zero agent effort. Events captured automatically.

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

If hooks can't reach Cairn, you'll see `{"error": "failed to reach cairn"}` in Claude Code's debug output.

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
- Increase the `timeout` value in settings.json (session-start: 15s, session-end: 30s)
- Check if Cairn is slow to respond (LLM synthesis can take time)
- For session-end, the narrative synthesis happens server-side — the hook just POSTs and returns

## Customization

- **Adjust batch size:** Set `CAIRN_EVENT_BATCH_SIZE` (default 25). Smaller = more frequent shipping, more digests. Larger = fewer HTTP calls.
- **Filter noisy tools:** Add a matcher to the PostToolUse config (e.g., `"matcher": "Bash|Edit|Write"`)
- **Skip event capture:** Remove the PostToolUse hook entirely — cairns still work, just without the event stream
- **Different project per directory:** Set `CAIRN_PROJECT` in each project's `.claude/settings.local.json`
- **Disable digestion:** Set `CAIRN_LLM_EVENT_DIGEST=false` — events still ship and store, but no LLM summaries. Cairn narratives fall back to raw events.
