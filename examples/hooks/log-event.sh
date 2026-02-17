#!/usr/bin/env bash
# Cairn Hook: PostToolUse (Event Bus)
# Fire-and-forget: POST each tool use directly to /api/events.
# No JSONL file, no offset tracking, no batch threshold.

set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"')

# Don't log if no session
[ -z "$SESSION_ID" ] && exit 0

CAIRN_URL="${CAIRN_URL:-http://localhost:8000}"
CAIRN_API_KEY="${CAIRN_API_KEY:-}"

# Build auth header if API key is set
AUTH_HEADER=()
if [ -n "$CAIRN_API_KEY" ]; then
    AUTH_HEADER=(-H "X-API-Key: ${CAIRN_API_KEY}")
fi

# Read session_name from env (set by session-start.sh) or derive it
SESSION_NAME="${CAIRN_SESSION_NAME:-}"
if [ -z "$SESSION_NAME" ]; then
    SHORT_ID="${SESSION_ID: -8}"
    SESSION_NAME="$(date -u +%Y-%m-%d)-${SHORT_ID}"
fi

# Read project from env or derive from cwd
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
CAIRN_PROJECT="${CAIRN_PROJECT:-$(basename "${CWD:-$(pwd)}")}"

# Capture tool_input (full JSON) and tool_response (capped at 2000 chars)
TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}')
TOOL_RESPONSE=$(echo "$INPUT" | jq -r '.tool_response // "" | tostring | .[0:2000]')

# Single POST to /api/events — fire-and-forget, backgrounded
(
    curl -sf -X POST "${CAIRN_URL}/api/events" \
        -H "Content-Type: application/json" \
        "${AUTH_HEADER[@]}" \
        -d "$(jq -nc \
            --arg session_name "$SESSION_NAME" \
            --arg event_type "tool_use" \
            --arg project "$CAIRN_PROJECT" \
            --arg agent_id "$SESSION_ID" \
            --arg tool_name "$TOOL_NAME" \
            --argjson tool_input "$TOOL_INPUT" \
            --arg tool_response "$TOOL_RESPONSE" \
            '{session_name: $session_name, event_type: $event_type, project: $project, agent_id: $agent_id, tool_name: $tool_name, payload: {tool_input: $tool_input, tool_response: $tool_response}}')" \
        >/dev/null 2>&1
) &

exit 0
