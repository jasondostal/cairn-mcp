#!/usr/bin/env bash
# Cairn Adapter: Cursor → session-end.sh
# Translates Cursor's session-end hook JSON to Cairn's contract.
#
# Cursor provides: { sessionId, workspaceFolder, reason, ... }
# Cairn expects:   { session_id, cwd, reason }

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

INPUT=$(cat)

# Translate field names (defensive: try Cursor names first, fall back to Cairn names)
TRANSLATED=$(echo "$INPUT" | jq '{
  session_id: (.sessionId // .session_id // "unknown"),
  cwd: (.workspaceFolder // .cwd // ""),
  reason: (.reason // "unknown")
}')

echo "$TRANSLATED" | "$CORE_DIR/session-end.sh"
