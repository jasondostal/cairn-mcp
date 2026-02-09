# Cairn Session Hooks

Automatic session capture using lifecycle hooks. Three scripts, zero manual effort.

## What it does

| Hook | When | What happens |
|------|------|-------------|
| `session-start.sh` | Session begins | Loads recent cairns as context, creates event log |
| `log-event.sh` | After every tool use | Appends a compact event record to a local temp file |
| `session-end.sh` | Session ends | Bundles events, sets a cairn via REST API |

Events are captured locally during the session (no HTTP calls per tool use — just file appends). At session end, everything gets bundled into a cairn with the full event log attached.

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

# After a session — cairn should exist with events:
curl -s http://YOUR_CAIRN_HOST:8000/api/cairns?limit=1 | jq '.[0] | {title, memory_count, has_events: (.events != null)}'
```

## Quick Start (Other MCP Clients)

The hooks are agent-agnostic bash scripts. Any AI coding agent with lifecycle hooks can use them.

**Contract:** Each script reads JSON from stdin and writes to stdout/stderr.

| Event | Stdin JSON | Script | What it does |
|-------|-----------|--------|-------------|
| Session start | `{"session_id": "...", "cwd": "..."}` | `session-start.sh` | Outputs cairn context to stdout, creates event log |
| Tool use | `{"session_id": "...", "tool_name": "...", "tool_input": {...}}` | `log-event.sh` | Appends event to local JSONL file (no HTTP) |
| Session end | `{"session_id": "...", "reason": "..."}` | `session-end.sh` | POSTs events to `/api/cairns`, archives event log |

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

## How it works

```
SessionStart hook
    |
    +-- GET /api/cairns?project=...&limit=5
    |   Returns recent cairns for context
    |
    +-- Output: session_name, active_project, recent cairn summaries
    |   (Agent reads this as session context)
    |
    +-- Create ~/.cairn/events/cairn-events-{session_id}.jsonl
        Write session_start event with session_name
         |
         |  +-------------------------------+
         +--| PostToolUse hook (every tool)  |
         |  | Append: {ts, tool, path, ...}  |
         |  | Local file only — no HTTP      |
         |  +-------------------------------+
         |         ... repeat ...
         |
SessionEnd hook
    |
    +-- Read event log -> JSON array
    +-- POST /api/cairns {project, session_name, events}
    |   |
    |   +-- Cairn already exists (agent set it via MCP)?
    |   |   -> Merge: attach events, re-synthesize narrative
    |   |
    |   +-- No cairn yet?
    |       -> Create cairn with events + stones + narrative
    |
    +-- Archive event log to ~/.cairn/events/archive/
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
# Event log should be archived (not deleted):
ls ~/.cairn/events/archive/

# Latest cairn should have events:
curl -s http://localhost:8000/api/cairns?limit=1 | jq '.[] | {id, title, has_events: (.events != null)}'

# Check a specific cairn's event count:
curl -s http://localhost:8000/api/cairns/1 | jq '{title, event_count: (.events | length), stone_count: (.stones | length)}'
```

### In the web UI

Open the Cairns page. Cairns with events will show a richer narrative that weaves together what the agent did (motes/events) with what it deliberately remembered (stones/memories).

## Troubleshooting

### Cairns exist but have no events

**Before v0.11.0:** This was a known race condition. The agent set the cairn via MCP before the session-end hook could POST events, and the hook got a 409 Conflict. Events were then deleted.

**Fix:** Upgrade to v0.11.0+. The cairn set endpoint now uses upsert semantics — both the agent and the hook can contribute to the same cairn without conflict.

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

- **Change what gets logged:** Edit the `case` block in `log-event.sh`
- **Filter noisy tools:** Add a matcher to the PostToolUse config (e.g., `"matcher": "Bash|Edit|Write"`)
- **Skip event capture:** Remove the PostToolUse hook entirely — cairns still work, just without the event log
- **Different project per directory:** Set `CAIRN_PROJECT` in each project's `.claude/settings.local.json`
