#!/usr/bin/env bash
# Cairn Hook: PostToolUse (Pipeline v2)
# Dumb pipe: capture full event → append to JSONL → ship batch when threshold reached.
#
# Captures: tool_name, tool_input (full JSON), tool_response (capped at 2000 chars)
# Ships batches of 25 events via background curl to POST /api/events/ingest.
# The .offset sidecar tracks what's been shipped.

set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"')

CAIRN_EVENT_DIR="${CAIRN_EVENT_DIR:-${HOME}/.cairn/events}"
EVENT_LOG="${CAIRN_EVENT_DIR}/cairn-events-${SESSION_ID}.jsonl"
OFFSET_FILE="${EVENT_LOG}.offset"

# Don't log if no session or no log file
[ -z "$SESSION_ID" ] && exit 0
[ ! -f "$EVENT_LOG" ] && exit 0

CAIRN_URL="${CAIRN_URL:-http://localhost:8000}"
CAIRN_API_KEY="${CAIRN_API_KEY:-}"
BATCH_SIZE="${CAIRN_EVENT_BATCH_SIZE:-25}"

# Build auth header if API key is set
AUTH_HEADER=()
if [ -n "$CAIRN_API_KEY" ]; then
    AUTH_HEADER=(-H "X-API-Key: ${CAIRN_API_KEY}")
fi

# Capture full event: tool_name, tool_input (full JSON), tool_response (capped)
TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}')
TOOL_RESPONSE=$(echo "$INPUT" | jq -r '.tool_response // "" | tostring | .[0:2000]')

# Append event as a single JSON line
jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       --arg type "tool_use" \
       --arg tool_name "$TOOL_NAME" \
       --argjson tool_input "$TOOL_INPUT" \
       --arg tool_response "$TOOL_RESPONSE" \
       '{ts: $ts, type: $type, tool_name: $tool_name, tool_input: $tool_input, tool_response: $tool_response}' >> "$EVENT_LOG"

# Count non-empty lines in the log (total events)
TOTAL_LINES=$(grep -c -v '^$' "$EVENT_LOG" 2>/dev/null || echo "0")

# Read shipped offset (how many lines have been shipped)
SHIPPED=0
if [ -f "$OFFSET_FILE" ]; then
    SHIPPED=$(cat "$OFFSET_FILE" 2>/dev/null || echo "0")
fi

UNSHIPPED=$((TOTAL_LINES - SHIPPED))

# Ship a batch if we've accumulated enough unshipped events
if [ "$UNSHIPPED" -ge "$BATCH_SIZE" ]; then
    # Read session_name from first event
    SESSION_NAME=$(grep -v '^$' "$EVENT_LOG" | head -1 | jq -r '.session_name // empty' 2>/dev/null || true)
    if [ -z "$SESSION_NAME" ]; then
        SHORT_ID="${SESSION_ID: -8}"
        SESSION_NAME="$(date -u +%Y-%m-%d)-${SHORT_ID}"
    fi

    # Read project and agent metadata from first event
    FIRST_EVENT=$(grep -v '^$' "$EVENT_LOG" | head -1)
    PROJECT=$(echo "$FIRST_EVENT" | jq -r '.project // empty' 2>/dev/null || true)
    CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
    PROJECT="${PROJECT:-$(basename "${CWD:-$(pwd)}")}"
    AGENT_ID=$(echo "$FIRST_EVENT" | jq -r '.agent_id // empty' 2>/dev/null || true)
    AGENT_TYPE=$(echo "$FIRST_EVENT" | jq -r '.agent_type // "interactive"' 2>/dev/null || true)
    PARENT_SESSION=$(echo "$FIRST_EVENT" | jq -r '.parent_session // empty' 2>/dev/null || true)

    # Calculate batch number (0-indexed)
    BATCH_NUMBER=$((SHIPPED / BATCH_SIZE))

    # Extract the unshipped events (skip first SHIPPED lines, take BATCH_SIZE)
    EVENTS=$(grep -v '^$' "$EVENT_LOG" | tail -n +"$((SHIPPED + 1))" | head -n "$BATCH_SIZE" | jq -s '.')

    # Build payload with agent metadata
    PAYLOAD=$(jq -nc \
        --arg project "$PROJECT" \
        --arg session_name "$SESSION_NAME" \
        --argjson batch_number "$BATCH_NUMBER" \
        --argjson events "$EVENTS" \
        --arg agent_id "$AGENT_ID" \
        --arg agent_type "$AGENT_TYPE" \
        --arg parent_session "$PARENT_SESSION" \
        '{project: $project, session_name: $session_name, batch_number: $batch_number, events: $events, agent_id: $agent_id, agent_type: $agent_type} + (if $parent_session != "" then {parent_session: $parent_session} else {} end)')

    # Ship in background — non-blocking, fire-and-forget
    # Only update offset on success (curl exit code 0)
    (
        if curl -sf -X POST "${CAIRN_URL}/api/events/ingest" \
            -H "Content-Type: application/json" \
            "${AUTH_HEADER[@]}" \
            -d "$PAYLOAD" >/dev/null 2>&1; then
            echo "$((SHIPPED + BATCH_SIZE))" > "$OFFSET_FILE"
        fi
    ) &
fi

exit 0
