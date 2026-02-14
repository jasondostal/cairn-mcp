#!/usr/bin/env bash
# Cairn Hook: SessionEnd (Pipeline v2)
# Ships any remaining unshipped events as a final batch, then sets a cairn.
#
# What it does:
#   1. Ships any unshipped events remaining in the log as a final batch
#   2. POSTs to /api/cairns WITHOUT events payload — server pulls digests from session_events
#   3. Archives event log + offset file to ~/.cairn/events/archive/
#
# Backward compatibility:
#   - If /api/events/ingest returns 404 (old server), events are shipped via POST /api/cairns
#     as the raw events payload (Pipeline v1 fallback)
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

CAIRN_EVENT_DIR="${CAIRN_EVENT_DIR:-${HOME}/.cairn/events}"
EVENT_LOG="${CAIRN_EVENT_DIR}/cairn-events-${SESSION_ID}.jsonl"
OFFSET_FILE="${EVENT_LOG}.offset"
BATCH_SIZE="${CAIRN_EVENT_BATCH_SIZE:-25}"

# Read session_name from the first event (session_start) in the log.
# This ensures start and end use the exact same value, even across midnight.
SESSION_NAME=""
if [ -f "$EVENT_LOG" ]; then
    SESSION_NAME=$(grep -v '^$' "$EVENT_LOG" | head -1 | jq -r '.session_name // empty' 2>/dev/null || true)
fi
# Fallback: recompute if event log is missing or has no session_name
if [ -z "$SESSION_NAME" ]; then
    SHORT_ID="${SESSION_ID: -8}"
    SESSION_NAME="$(date -u +%Y-%m-%d)-${SHORT_ID}"
fi

# Log the session end event
if [ -f "$EVENT_LOG" ]; then
    jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
           --arg type "session_end" \
           --arg reason "$(echo "$INPUT" | jq -r '.reason // "unknown"')" \
           '{ts: $ts, type: $type, reason: $reason}' >> "$EVENT_LOG"
fi

# Ship any remaining unshipped events as final batch(es)
V2_AVAILABLE=true
if [ -f "$EVENT_LOG" ]; then
    TOTAL_LINES=$(grep -c -v '^$' "$EVENT_LOG" 2>/dev/null || echo "0")

    SHIPPED=0
    if [ -f "$OFFSET_FILE" ]; then
        SHIPPED=$(cat "$OFFSET_FILE" 2>/dev/null || echo "0")
    fi

    UNSHIPPED=$((TOTAL_LINES - SHIPPED))

    if [ "$UNSHIPPED" -gt 0 ]; then
        # Calculate batch number
        BATCH_NUMBER=$((SHIPPED / BATCH_SIZE))

        # Extract remaining events
        EVENTS=$(grep -v '^$' "$EVENT_LOG" | tail -n +"$((SHIPPED + 1))" | jq -s '.')

        PAYLOAD=$(jq -nc \
            --arg project "$CAIRN_PROJECT" \
            --arg session_name "$SESSION_NAME" \
            --argjson batch_number "$BATCH_NUMBER" \
            --argjson events "$EVENTS" \
            '{project: $project, session_name: $session_name, batch_number: $batch_number, events: $events}')

        # Ship final batch — synchronous this time (we're at session end)
        HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" -X POST "${CAIRN_URL}/api/events/ingest" \
            -H "Content-Type: application/json" \
            "${AUTH_HEADER[@]}" \
            -d "$PAYLOAD" 2>/dev/null || echo "000")

        if [ "$HTTP_CODE" = "202" ] || [ "$HTTP_CODE" = "200" ]; then
            echo "$TOTAL_LINES" > "$OFFSET_FILE"
        elif [ "$HTTP_CODE" = "404" ]; then
            # Old server — /api/events/ingest doesn't exist
            V2_AVAILABLE=false
        fi
    fi
fi

# Set the cairn via POST /api/cairns
if [ "$V2_AVAILABLE" = true ]; then
    # Pipeline v2: server pulls digests from session_events — no events payload needed
    PAYLOAD=$(jq -nc \
        --arg project "$CAIRN_PROJECT" \
        --arg session_name "$SESSION_NAME" \
        '{project: $project, session_name: $session_name}')
else
    # Pipeline v1 fallback: ship raw events in cairn payload
    EVENTS="[]"
    if [ -f "$EVENT_LOG" ]; then
        EVENTS=$(grep -v '^$' "$EVENT_LOG" | jq -s '.' 2>/dev/null || echo "[]")
    fi
    PAYLOAD=$(jq -nc \
        --arg project "$CAIRN_PROJECT" \
        --arg session_name "$SESSION_NAME" \
        --argjson events "$EVENTS" \
        '{project: $project, session_name: $session_name, events: $events}')
fi

RESULT=$(curl -sf -X POST "${CAIRN_URL}/api/cairns" \
    -H "Content-Type: application/json" \
    "${AUTH_HEADER[@]}" \
    -d "$PAYLOAD" \
    2>/dev/null || echo '{"error": "failed to reach cairn"}')

# Archive event log + offset file (preserve for replay/debugging)
ARCHIVE_DIR="${CAIRN_EVENT_DIR}/archive"
mkdir -p "$ARCHIVE_DIR"
mv "$EVENT_LOG" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$OFFSET_FILE" "$ARCHIVE_DIR/" 2>/dev/null || true

EVENT_COUNT=0
if [ -f "$EVENT_LOG" ]; then
    EVENT_COUNT=$(grep -c -v '^$' "$EVENT_LOG" 2>/dev/null || echo "0")
fi

# Log result to stderr (visible in debug mode)
echo "Cairn set for session ${SESSION_NAME}: $(echo "$RESULT" | jq -r '.title // .error // "unknown"' 2>/dev/null)" >&2

exit 0
