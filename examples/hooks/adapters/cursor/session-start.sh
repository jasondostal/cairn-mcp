#!/usr/bin/env bash
# Cairn Adapter: Cursor → session-start.sh
# Translates Cursor's session-start hook JSON to Cairn's contract.
#
# Cursor provides: { sessionId, workspaceFolder, ... }
# Cairn expects:   { session_id, cwd }

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

INPUT=$(cat)

# Translate field names (defensive: try Cursor names first, fall back to Cairn names)
TRANSLATED=$(echo "$INPUT" | jq '{
  session_id: (.sessionId // .session_id // "unknown"),
  cwd: (.workspaceFolder // .cwd // "")
}')

echo "$TRANSLATED" | "$CORE_DIR/session-start.sh"
