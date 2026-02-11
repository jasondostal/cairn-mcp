#!/usr/bin/env bash
# Cairn Adapter: Windsurf → log-event.sh (with session auto-init)
# Translates Windsurf's post-mcp-tool-use hook JSON to Cairn's contract.
#
# Windsurf only has post_mcp_tool_use — no session start/end hooks.
# This adapter auto-initializes the session on first tool use by detecting
# whether an event log already exists for the current session.
#
# Windsurf provides: { sessionId, toolName, toolInput, toolResponse, workspaceFolder, ... }
# Cairn expects:     { session_id, tool_name, tool_input, tool_response, cwd }
#
# Limitation: No session-end hook. The agent must call cairns(action="set")
# directly (Tier 2), or the user runs session-end.sh manually.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

INPUT=$(cat)

# Extract session ID (defensive fallbacks)
SESSION_ID=$(echo "$INPUT" | jq -r '.sessionId // .session_id // "unknown"')
CWD=$(echo "$INPUT" | jq -r '.workspaceFolder // .cwd // ""')

CAIRN_EVENT_DIR="${CAIRN_EVENT_DIR:-${HOME}/.cairn/events}"
EVENT_LOG="${CAIRN_EVENT_DIR}/cairn-events-${SESSION_ID}.jsonl"

# Auto-init session on first tool use (no event log exists yet)
if [ ! -f "$EVENT_LOG" ]; then
    START_INPUT=$(jq -nc --arg session_id "$SESSION_ID" --arg cwd "$CWD" \
        '{session_id: $session_id, cwd: $cwd}')
    echo "$START_INPUT" | "$CORE_DIR/session-start.sh" >/dev/null 2>&1 || true
fi

# Translate and forward to log-event.sh
TRANSLATED=$(echo "$INPUT" | jq '{
  session_id: (.sessionId // .session_id // "unknown"),
  tool_name: (.toolName // .tool_name // "unknown"),
  tool_input: (.toolInput // .tool_input // {}),
  tool_response: (.toolResponse // .tool_response // ""),
  cwd: (.workspaceFolder // .cwd // "")
}')

echo "$TRANSLATED" | "$CORE_DIR/log-event.sh"
