#!/usr/bin/env bash
# Cairn Hook: SessionEnd
# Publishes session_end event and closes the session. No batch shipping, no digestion.
#
# What it does:
#   1. POSTs session_end event to /api/events
#   2. Calls POST /api/sessions/{name}/close to set closed_at
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

# Read session_name from env (set by session-start.sh) or derive it
SESSION_NAME="${CAIRN_SESSION_NAME:-}"
if [ -z "$SESSION_NAME" ]; then
    SHORT_ID="${SESSION_ID: -8}"
    SESSION_NAME="$(date -u +%Y-%m-%d)-${SHORT_ID}"
fi

REASON=$(echo "$INPUT" | jq -r '.reason // "unknown"')

# Publish session_end event
curl -sf -X POST "${CAIRN_URL}/api/events" \
    -H "Content-Type: application/json" \
    "${AUTH_HEADER[@]}" \
    -d "$(jq -nc \
        --arg session_name "$SESSION_NAME" \
        --arg event_type "session_end" \
        --arg project "$CAIRN_PROJECT" \
        --arg agent_id "$SESSION_ID" \
        --arg reason "$REASON" \
        '{session_name: $session_name, event_type: $event_type, project: $project, agent_id: $agent_id, payload: {reason: $reason}}')" \
    >/dev/null 2>&1 || true

# Close the session — sets closed_at, no LLM
curl -sf -X POST "${CAIRN_URL}/api/sessions/${SESSION_NAME}/close" \
    -H "Content-Type: application/json" \
    "${AUTH_HEADER[@]}" \
    >/dev/null 2>&1 || true

echo "Cairn session closed: ${SESSION_NAME}" >&2

exit 0
