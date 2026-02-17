#!/usr/bin/env bash
# Cairn Hook Setup Script
# Interactive setup for Claude Code session capture hooks.
#
# Usage: ./scripts/setup-hooks.sh [CAIRN_URL]

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[info]${NC} $*"; }
ok()    { echo -e "${GREEN}[ok]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
fail()  { echo -e "${RED}[fail]${NC} $*"; }

echo ""
echo "========================================="
echo "  Cairn Hook Setup"
echo "  Session capture for Claude Code"
echo "========================================="
echo ""

# ──────────────────────────────────────────────
# Step 1: Check dependencies
# ──────────────────────────────────────────────

info "Checking dependencies..."

MISSING=""
for cmd in jq curl; do
    if command -v "$cmd" &>/dev/null; then
        ok "$cmd found: $(command -v "$cmd")"
    else
        fail "$cmd not found"
        MISSING="$MISSING $cmd"
    fi
done

if [ -n "$MISSING" ]; then
    echo ""
    fail "Missing dependencies:$MISSING"
    echo "  Install them before continuing:"
    echo "    macOS:        brew install$MISSING"
    echo "    Ubuntu/Debian: sudo apt-get install$MISSING"
    exit 1
fi
echo ""

# ──────────────────────────────────────────────
# Step 2: Detect/ask for CAIRN_URL
# ──────────────────────────────────────────────

CAIRN_URL="${1:-${CAIRN_URL:-}}"

if [ -z "$CAIRN_URL" ]; then
    echo -n "Cairn API URL [http://localhost:8000]: "
    read -r CAIRN_URL
    CAIRN_URL="${CAIRN_URL:-http://localhost:8000}"
fi

# Strip trailing slash
CAIRN_URL="${CAIRN_URL%/}"

info "Testing connectivity to $CAIRN_URL..."

STATUS=$(curl -sf --max-time 5 "$CAIRN_URL/api/status" 2>/dev/null || echo "")
if [ -n "$STATUS" ]; then
    ok "Cairn is reachable"
    echo "  $(echo "$STATUS" | jq -r '"  Memories: \(.memory_count // "?"), Projects: \(.project_count // "?")"' 2>/dev/null || echo "  (status parsed)")"
else
    warn "Could not reach $CAIRN_URL/api/status"
    echo "  Cairn may not be running yet. Setup will continue."
    echo "  Make sure Cairn is running before starting a session."
    echo ""
fi
echo ""

# ──────────────────────────────────────────────
# Step 3: Find hook scripts
# ──────────────────────────────────────────────

# Try to find the hooks relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$REPO_DIR/examples/hooks"

if [ ! -f "$HOOKS_DIR/session-start.sh" ]; then
    fail "Could not find hook scripts at $HOOKS_DIR"
    echo "  Expected: $HOOKS_DIR/session-start.sh"
    echo "  Run this script from the cairn repo root."
    exit 1
fi

# Ensure hooks are executable
chmod +x "$HOOKS_DIR/session-start.sh" "$HOOKS_DIR/log-event.sh" "$HOOKS_DIR/session-end.sh"
ok "Hook scripts found at $HOOKS_DIR"
echo ""

# ──────────────────────────────────────────────
# Step 4: Generate settings.json snippet
# ──────────────────────────────────────────────

info "Generating Claude Code settings snippet..."
echo ""

SETTINGS=$(cat <<EOF
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "CAIRN_URL=$CAIRN_URL $HOOKS_DIR/session-start.sh",
            "timeout": 15
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "CAIRN_URL=$CAIRN_URL $HOOKS_DIR/log-event.sh",
            "timeout": 5
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "CAIRN_URL=$CAIRN_URL $HOOKS_DIR/session-end.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
EOF
)

echo "Add this to ~/.claude/settings.json (global) or .claude/settings.local.json (project):"
echo ""
echo "$SETTINGS" | jq .
echo ""

# ──────────────────────────────────────────────
# Step 5: Optional pipeline test
# ──────────────────────────────────────────────

echo -n "Run a pipeline test? (publishes a test event) [y/N]: "
read -r DO_TEST

if [[ "$DO_TEST" =~ ^[Yy] ]]; then
    echo ""
    info "Testing event bus pipeline..."

    TEST_SESSION="setup-test-$(date +%s)"
    TEST_PROJECT="cairn-setup-test"

    # Publish a session_start event (should also create a session record)
    RESULT=$(curl -sf -X POST "$CAIRN_URL/api/events" \
        -H "Content-Type: application/json" \
        -d "{\"session_name\": \"$TEST_SESSION\", \"event_type\": \"session_start\", \"project\": \"$TEST_PROJECT\", \"payload\": {\"agent_type\": \"setup-test\"}}" \
        2>/dev/null || echo '{"error": "failed"}')

    if echo "$RESULT" | jq -e '.id' &>/dev/null; then
        EVENT_ID=$(echo "$RESULT" | jq -r '.id')
        ok "Event published (id=$EVENT_ID)"

        # Verify event is queryable
        VERIFY=$(curl -sf "$CAIRN_URL/api/events?session_name=$TEST_SESSION" 2>/dev/null || echo "")
        if [ -n "$VERIFY" ]; then
            EVENT_COUNT=$(echo "$VERIFY" | jq -r '.count // 0' 2>/dev/null)
            ok "Verified: $EVENT_COUNT event(s) for session"
        fi

        # Verify session was auto-created
        SESSIONS=$(curl -sf "$CAIRN_URL/api/sessions?project=$TEST_PROJECT" 2>/dev/null || echo "")
        if echo "$SESSIONS" | jq -e '.items[0].session_name' &>/dev/null; then
            ok "Session record created automatically"
        else
            warn "Session record not found (may need migration 025)"
        fi
    else
        fail "Test failed: $(echo "$RESULT" | jq -r '.error // .detail // "unknown error"' 2>/dev/null)"
    fi
    echo ""
fi

# ──────────────────────────────────────────────
# Done
# ──────────────────────────────────────────────

echo "========================================="
echo "  Setup complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Add the settings snippet above to your Claude Code config"
echo "  2. Start a new Claude Code session"
echo "  3. After the session, check: curl -s $CAIRN_URL/api/sessions | jq ."
echo ""
echo "Documentation: $HOOKS_DIR/README.md"
echo ""
