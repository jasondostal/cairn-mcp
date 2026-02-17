#!/usr/bin/env bash
# Cairn Hook: SessionStart
# Opens a session and publishes a session_start event via the event bus.
#
# What it does:
#   1. POSTs session_start event to /api/events
#   2. Exports CAIRN_SESSION_NAME for other hooks to use
#   3. Outputs session_name and project for Claude to use when storing memories
#
# Configuration (env vars):
#   CAIRN_URL      — Cairn API base URL (default: http://localhost:8000)
#   CAIRN_PROJECT  — Project name (default: derived from cwd basename)

set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

CAIRN_URL="${CAIRN_URL:-http://localhost:8000}"
CAIRN_API_KEY="${CAIRN_API_KEY:-}"
CAIRN_PROJECT="${CAIRN_PROJECT:-$(basename "${CWD:-$(pwd)}")}"

# Build auth header if API key is set
AUTH_HEADER=()
if [ -n "$CAIRN_API_KEY" ]; then
    AUTH_HEADER=(-H "X-API-Key: ${CAIRN_API_KEY}")
fi

# Build session_name from date + session ID (last 8 chars for readability)
SHORT_ID="${SESSION_ID: -8}"
SESSION_NAME="$(date -u +%Y-%m-%d)-${SHORT_ID}"

# Agent metadata — interactive sessions from Claude Code
AGENT_TYPE="${CAIRN_AGENT_TYPE:-interactive}"
PARENT_SESSION="${CAIRN_PARENT_SESSION:-}"

# Export for other hooks (log-event.sh, session-end.sh)
export CAIRN_SESSION_NAME="$SESSION_NAME"

# Publish session_start event (fire-and-forget, backgrounded)
curl -sf -X POST "${CAIRN_URL}/api/events" \
    -H "Content-Type: application/json" \
    "${AUTH_HEADER[@]}" \
    -d "$(jq -nc \
        --arg session_name "$SESSION_NAME" \
        --arg event_type "session_start" \
        --arg project "$CAIRN_PROJECT" \
        --arg agent_id "$SESSION_ID" \
        --arg agent_type "$AGENT_TYPE" \
        --arg parent_session "$PARENT_SESSION" \
        '{session_name: $session_name, event_type: $event_type, project: $project, agent_id: $agent_id, payload: {agent_type: $agent_type, parent_session: $parent_session}}')" \
    >/dev/null 2>&1 &

# Output session context — Claude Code adds stdout from SessionStart hooks to context
echo "Session name for this session: ${SESSION_NAME}"
echo "Active project: ${CAIRN_PROJECT}"
echo "Use this as session_name when storing memories via cairn."

exit 0
