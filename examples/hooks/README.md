# Cairn Session Hooks

Automatic session capture using lifecycle hooks. Three scripts, zero manual effort.

## What it does

| Hook | When | What happens |
|------|------|-------------|
| `session-start.sh` | Session begins | Loads recent cairns as context, creates event log |
| `log-event.sh` | After every tool use | Appends a compact event record to a local temp file |
| `session-end.sh` | Session ends | Bundles events, sets a cairn via MCP |

Events are captured locally during the session (no HTTP calls per tool use — just file appends). At session end, everything gets bundled into a cairn with the full event log attached.

Event logs are stored in `~/.cairn/events/` by default (created automatically). Override with `CAIRN_EVENT_DIR` to use a different location.

## Setup

1. Copy `settings.json` into your project's `.claude/settings.json` (or merge with existing):

```bash
mkdir -p .claude
cp examples/hooks/settings.json .claude/settings.json
```

2. Or merge the hooks config into your user-level settings:

```bash
# Edit ~/.claude/settings.json and add the hooks block
```

3. Set environment variables (optional — defaults work for local setup):

```bash
export CAIRN_URL="http://localhost:8000"      # default
export CAIRN_PROJECT="my-project"             # default: cwd basename
export CAIRN_EVENT_DIR="$HOME/.cairn/events"  # default
```

## How it works

```
SessionStart
    │
    ├─ Fetch recent cairns via GET /api/cairns?project=...
    ├─ Output context for Claude to load
    └─ Create ~/.cairn/events/cairn-events-{session_id}.jsonl
         │
         │  ┌─────────────────────────────────┐
         ├──│ PostToolUse (async, every tool)  │
         │  │ Append: {ts, tool, summary}      │
         │  └─────────────────────────────────┘
         │         ... repeat ...
         │
SessionEnd
    │
    ├─ Read event log → JSON array
    ├─ POST cairns(action="set") with events
    └─ Clean up temp file
```

## The three tiers

These hooks are **Tier 3** — fully automatic. Cairn works at all three tiers:

- **Tier 1 (Organic):** Agent follows behavioral rules, stores memories with `session_name`, sets cairns manually. No hooks needed.
- **Tier 2 (Tool-assisted):** Agent calls `cairns(action="set")` at session end. One tool call.
- **Tier 3 (Hook-automated):** These scripts. Zero agent effort. Events captured automatically.

Each tier is additive. If hooks aren't installed, Tier 2 still works. If the agent forgets to set a cairn, Tier 1 memories still exist.

## Requirements

- `jq` (JSON processing)
- `curl` (HTTP calls to Cairn API)
- Cairn MCP server running and accessible

## Agent compatibility

These hooks are confirmed working with **Claude Code** but are agent-agnostic by design. They're just bash scripts that read JSON from stdin and talk to a REST API via curl. Any AI coding agent with lifecycle hooks (or equivalent session start/end events) can use them — just wire up the same triggers:

- **SessionStart** → `session-start.sh` (pass `{"session_id": "...", "cwd": "..."}` on stdin)
- **PostToolUse** → `log-event.sh` (pass `{"session_id": "...", "tool_name": "...", "tool_input": {...}}` on stdin)
- **SessionEnd** → `session-end.sh` (pass `{"session_id": "..."}` on stdin)

The only requirement is a unique `session_id` per session and `jq` + `curl` on the system.

## Customization

- **Change what gets logged:** Edit the `case` block in `log-event.sh`
- **Filter noisy tools:** Add a matcher to the PostToolUse config (e.g., `"matcher": "Bash|Edit|Write"`)
- **Skip event capture:** Remove the PostToolUse hook entirely — cairns still work, just without the event log
