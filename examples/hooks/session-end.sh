#!/usr/bin/env bash
# Cairn Hook: SessionEnd
# Ships any remaining unshipped events as a final batch, then closes the session.
#
# What it does:
#   1. Ships any unshipped events remaining in the log as a final batch
#   2. POSTs to /api/sessions/{name}/close — digests pending batches and stores
#      them as progress memories, feeding the knowledge graph
#   3. Archives event log + offset file to ~/.cairn/events/archive/
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

# Ship any remaining unshipped events as final batch
if [ -f "$EVENT_LOG" ]; then
    TOTAL_LINES=$(grep -c -v '^$' "$EVENT_LOG" 2>/dev/null || echo "0")

    SHIPPED=0
    if [ -f "$OFFSET_FILE" ]; then
        SHIPPED=$(cat "$OFFSET_FILE" 2>/dev/null || echo "0")
    fi

    UNSHIPPED=$((TOTAL_LINES - SHIPPED))

    if [ "$UNSHIPPED" -gt 0 ]; then
        BATCH_NUMBER=$((SHIPPED / BATCH_SIZE))

        EVENTS=$(grep -v '^$' "$EVENT_LOG" | tail -n +"$((SHIPPED + 1))" | jq -s '.')

        PAYLOAD=$(jq -nc \
            --arg project "$CAIRN_PROJECT" \
            --arg session_name "$SESSION_NAME" \
            --argjson batch_number "$BATCH_NUMBER" \
            --argjson events "$EVENTS" \
            '{project: $project, session_name: $session_name, batch_number: $batch_number, events: $events}')

        # Ship final batch — synchronous (we're at session end)
        HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" -X POST "${CAIRN_URL}/api/events/ingest" \
            -H "Content-Type: application/json" \
            "${AUTH_HEADER[@]}" \
            -d "$PAYLOAD" 2>/dev/null || echo "000")

        if [ "$HTTP_CODE" = "202" ] || [ "$HTTP_CODE" = "200" ]; then
            echo "$TOTAL_LINES" > "$OFFSET_FILE"
        fi
    fi
fi

# Close the session — digests pending batches and stores them as graph knowledge
RESULT=$(curl -sf -X POST "${CAIRN_URL}/api/sessions/${SESSION_NAME}/close" \
    -H "Content-Type: application/json" \
    "${AUTH_HEADER[@]}" \
    2>/dev/null || echo '{"error": "failed to reach cairn"}')

# Archive event log + offset file (preserve for replay/debugging)
ARCHIVE_DIR="${CAIRN_EVENT_DIR}/archive"
mkdir -p "$ARCHIVE_DIR"
mv "$EVENT_LOG" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$OFFSET_FILE" "$ARCHIVE_DIR/" 2>/dev/null || true

# Log result to stderr (visible in debug mode)
DIGESTED=$(echo "$RESULT" | jq -r '.digested // "?"' 2>/dev/null)
echo "Cairn session closed: ${SESSION_NAME} (digested: ${DIGESTED})" >&2

exit 0
