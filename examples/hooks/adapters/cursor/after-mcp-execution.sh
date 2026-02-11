#!/usr/bin/env bash
# Cairn Adapter: Cursor → log-event.sh
# Translates Cursor's after-mcp-execution hook JSON to Cairn's contract.
#
# Cursor provides: { sessionId, toolName, toolInput, toolResponse, workspaceFolder, ... }
# Cairn expects:   { session_id, tool_name, tool_input, tool_response, cwd }

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

INPUT=$(cat)

# Translate field names (defensive: try Cursor names first, fall back to Cairn names)
TRANSLATED=$(echo "$INPUT" | jq '{
  session_id: (.sessionId // .session_id // "unknown"),
  tool_name: (.toolName // .tool_name // "unknown"),
  tool_input: (.toolInput // .tool_input // {}),
  tool_response: (.toolResponse // .tool_response // ""),
  cwd: (.workspaceFolder // .cwd // "")
}')

echo "$TRANSLATED" | "$CORE_DIR/log-event.sh"
