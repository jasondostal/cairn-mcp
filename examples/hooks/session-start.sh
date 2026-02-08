#!/usr/bin/env bash
# Cairn Hook: SessionStart
# Loads recent cairn context and initializes the session event log.
#
# What it does:
#   1. Fetches the most recent cairns for the project via REST API
#   2. Creates a fresh event log file for this session
#   3. Outputs context for Claude to load silently
#
# Configuration (env vars):
#   CAIRN_URL      — Cairn API base URL (default: http://localhost:8002)
#   CAIRN_PROJECT  — Project name (default: derived from cwd basename)

set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

CAIRN_URL="${CAIRN_URL:-http://localhost:8002}"
CAIRN_PROJECT="${CAIRN_PROJECT:-$(basename "${CWD:-$(pwd)}")}"

# Session event log — one JSONL file per session
EVENT_LOG="/tmp/cairn-events-${SESSION_ID}.jsonl"
echo "" > "$EVENT_LOG"

# Log the session start event
jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       --arg type "session_start" \
       --arg session "$SESSION_ID" \
       --arg project "$CAIRN_PROJECT" \
       '{ts: $ts, type: $type, session: $session, project: $project}' >> "$EVENT_LOG"

# Fetch recent cairns for context
CAIRNS=$(curl -sf "${CAIRN_URL}/api/cairns?project=${CAIRN_PROJECT}&limit=3" 2>/dev/null || echo "[]")

# Build context output for Claude
CAIRN_COUNT=$(echo "$CAIRNS" | jq 'length' 2>/dev/null || echo "0")

if [ "$CAIRN_COUNT" -gt 0 ]; then
    CONTEXT="Recent session history for ${CAIRN_PROJECT}:\n"
    CONTEXT+=$(echo "$CAIRNS" | jq -r '.[] | "- [\(.set_at // "unknown")] \(.title // "Untitled") (\(.memory_count) stones)\n  \(.narrative // "No narrative")\n"' 2>/dev/null || echo "")

    # Output context — Claude Code adds stdout from SessionStart hooks to context
    echo "$CONTEXT"
fi

exit 0
