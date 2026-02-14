#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-localhost:8000}"
BASE="http://$HOST"

echo "=== Smoke testing $BASE ==="

# Check /api/status
echo -n "Status endpoint... "
status=$(curl -sf "$BASE/api/status") || { echo "FAIL (not reachable)"; exit 1; }
echo "OK"
version=$(echo "$status" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','unknown'))" 2>/dev/null || echo "unknown")
memories=$(echo "$status" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_memories','?'))" 2>/dev/null || echo "?")
echo "  Version: $version"
echo "  Memories: $memories"

# Check /mcp endpoint exists
echo -n "MCP endpoint... "
mcp_code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/mcp" 2>/dev/null || echo "000")
if [ "$mcp_code" = "200" ] || [ "$mcp_code" = "405" ]; then
  echo "OK ($mcp_code)"
else
  echo "WARN (HTTP $mcp_code)"
fi

echo "=== Smoke test passed ==="
