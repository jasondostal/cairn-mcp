#!/usr/bin/env bash
# Cairn Hook: PostToolUse
# Appends a lightweight event record to the session log.
# Runs async — no blocking, no HTTP calls. Just a local file append.
#
# Captures: tool name, timestamp, and a compact summary of the action.
# The full event log gets bundled into the cairn at session end.

set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"')

EVENT_LOG="/tmp/cairn-events-${SESSION_ID}.jsonl"

# Don't log if no session or no log file
[ -z "$SESSION_ID" ] && exit 0
[ ! -f "$EVENT_LOG" ] && exit 0

# Extract a compact summary based on tool type
case "$TOOL_NAME" in
    Bash)
        SUMMARY=$(echo "$INPUT" | jq -r '.tool_input.command // "" | .[0:120]')
        ;;
    Read)
        SUMMARY=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
        ;;
    Edit|Write)
        SUMMARY=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
        ;;
    Glob)
        SUMMARY=$(echo "$INPUT" | jq -r '.tool_input.pattern // ""')
        ;;
    Grep)
        SUMMARY=$(echo "$INPUT" | jq -r '.tool_input.pattern // ""')
        ;;
    mcp__cairn__*)
        ACTION=$(echo "$INPUT" | jq -r '.tool_input.action // .tool_input.query // "" | .[0:120]')
        SUMMARY="cairn: ${TOOL_NAME##mcp__cairn__} ${ACTION}"
        ;;
    Task)
        SUMMARY=$(echo "$INPUT" | jq -r '.tool_input.description // "" | .[0:120]')
        ;;
    *)
        SUMMARY=$(echo "$INPUT" | jq -r '.tool_input | keys | join(", ") | .[0:80]' 2>/dev/null || echo "")
        ;;
esac

# Append event as a single JSON line
jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       --arg type "tool_use" \
       --arg tool "$TOOL_NAME" \
       --arg summary "$SUMMARY" \
       '{ts: $ts, type: $type, tool: $tool, summary: $summary}' >> "$EVENT_LOG"

exit 0
