#!/usr/bin/env bash
# Cairn Hook: SessionStart
# Initializes the session event log and outputs boot context.
#
# What it does:
#   1. Creates a fresh event log file for this session
#   2. Outputs session_name and project for Claude to use when storing memories
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

# Session event log — one JSONL file per session
CAIRN_EVENT_DIR="${CAIRN_EVENT_DIR:-${HOME}/.cairn/events}"
mkdir -p "$CAIRN_EVENT_DIR"
EVENT_LOG="${CAIRN_EVENT_DIR}/cairn-events-${SESSION_ID}.jsonl"
OFFSET_FILE="${EVENT_LOG}.offset"
echo "" > "$EVENT_LOG"
echo "0" > "$OFFSET_FILE"

# Agent metadata — interactive sessions from Claude Code
AGENT_TYPE="${CAIRN_AGENT_TYPE:-interactive}"
PARENT_SESSION="${CAIRN_PARENT_SESSION:-}"

# Log the session start event (includes session_name so session-end.sh can read it back)
jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       --arg type "session_start" \
       --arg session "$SESSION_ID" \
       --arg project "$CAIRN_PROJECT" \
       --arg session_name "$SESSION_NAME" \
       --arg agent_id "$SESSION_ID" \
       --arg agent_type "$AGENT_TYPE" \
       --arg parent_session "$PARENT_SESSION" \
       '{ts: $ts, type: $type, session: $session, project: $project, session_name: $session_name, agent_id: $agent_id, agent_type: $agent_type, parent_session: $parent_session}' >> "$EVENT_LOG"

# Output session context — Claude Code adds stdout from SessionStart hooks to context
echo "Session name for this session: ${SESSION_NAME}"
echo "Active project: ${CAIRN_PROJECT}"
echo "Use this as session_name when storing memories via cairn."

exit 0
