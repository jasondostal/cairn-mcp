#!/usr/bin/env bash
# Cairn Hook: SessionEnd
# Bundles the session event log and sets a cairn via the REST API.
#
# What it does:
#   1. Reads the session event log (JSONL → JSON array)
#   2. POSTs to /api/cairns to set the cairn with events attached
#   3. Archives the event log to ~/.cairn/events/archive/
#
# Configuration (env vars):
#   CAIRN_URL      — Cairn API base URL (default: http://localhost:8002)
#   CAIRN_PROJECT  — Project name (default: derived from cwd basename)

set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

CAIRN_URL="${CAIRN_URL:-http://localhost:8000}"
CAIRN_PROJECT="${CAIRN_PROJECT:-$(basename "${CWD:-$(pwd)}")}"

CAIRN_EVENT_DIR="${CAIRN_EVENT_DIR:-${HOME}/.cairn/events}"
EVENT_LOG="${CAIRN_EVENT_DIR}/cairn-events-${SESSION_ID}.jsonl"

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

# Read events from log file (JSONL → JSON array)
EVENTS="[]"
if [ -f "$EVENT_LOG" ]; then
    # Filter empty lines and convert JSONL to array
    EVENTS=$(grep -v '^$' "$EVENT_LOG" | jq -s '.' 2>/dev/null || echo "[]")
fi

EVENT_COUNT=$(echo "$EVENTS" | jq 'length' 2>/dev/null || echo "0")

# Log the session end event
if [ -f "$EVENT_LOG" ]; then
    jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
           --arg type "session_end" \
           --arg reason "$(echo "$INPUT" | jq -r '.reason // "unknown"')" \
           '{ts: $ts, type: $type, reason: $reason}' >> "$EVENT_LOG"

    # Re-read with the end event included
    EVENTS=$(grep -v '^$' "$EVENT_LOG" | jq -s '.' 2>/dev/null || echo "[]")
fi

# Set the cairn via POST /api/cairns
PAYLOAD=$(jq -nc \
    --arg project "$CAIRN_PROJECT" \
    --arg session_name "$SESSION_NAME" \
    --argjson events "$EVENTS" \
    '{project: $project, session_name: $session_name, events: $events}')

RESULT=$(curl -sf -X POST "${CAIRN_URL}/api/cairns" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    2>/dev/null || echo '{"error": "failed to reach cairn"}')

# Archive event log (preserve for replay/debugging)
ARCHIVE_DIR="${CAIRN_EVENT_DIR}/archive"
mkdir -p "$ARCHIVE_DIR"
mv "$EVENT_LOG" "$ARCHIVE_DIR/" 2>/dev/null || true

# Log result to stderr (visible in debug mode)
echo "Cairn set for session ${SESSION_NAME} (${EVENT_COUNT} events): $(echo "$RESULT" | jq -r '.title // .error // "unknown"' 2>/dev/null)" >&2

exit 0
