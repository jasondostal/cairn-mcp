#!/usr/bin/env bash
# Cairn Multi-IDE Setup Script
# Detects installed IDEs, configures MCP connections, and optionally installs hook adapters.
#
# Usage: ./scripts/setup.sh [--dry-run] [CAIRN_URL]
#
# Supports: Claude Code, Cursor, Windsurf, Cline (VS Code), Continue

set -euo pipefail

# ──────────────────────────────────────────────
# Colors and helpers
# ──────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}[info]${NC} $*"; }
ok()    { echo -e "${GREEN}  [ok]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
fail()  { echo -e "${RED}[fail]${NC} $*"; }
header() { echo -e "\n${BOLD}$*${NC}"; }

DRY_RUN=false
CAIRN_URL=""
CONFIGURED_IDES=()

# ──────────────────────────────────────────────
# Parse arguments
# ──────────────────────────────────────────────

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --help|-h)
            echo "Usage: $(basename "$0") [--dry-run] [CAIRN_URL]"
            echo ""
            echo "Options:"
            echo "  --dry-run    Show what would be written without making changes"
            echo "  CAIRN_URL    Cairn API base URL (default: http://localhost:8000)"
            exit 0
            ;;
        *) CAIRN_URL="$arg" ;;
    esac
done

# ──────────────────────────────────────────────
# Banner
# ──────────────────────────────────────────────

echo ""
echo "========================================="
echo "  Cairn Setup"
echo "  MCP memory for any IDE"
echo "========================================="
echo ""

if [ "$DRY_RUN" = true ]; then
    warn "DRY RUN — no files will be written"
    echo ""
fi

# ──────────────────────────────────────────────
# Step 1: Check dependencies
# ──────────────────────────────────────────────

header "Checking dependencies..."

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
    echo "    macOS:         brew install$MISSING"
    echo "    Ubuntu/Debian: sudo apt-get install$MISSING"
    exit 1
fi

# ──────────────────────────────────────────────
# Step 2: Detect/ask for CAIRN_URL
# ──────────────────────────────────────────────

CAIRN_URL="${CAIRN_URL:-${CAIRN_URL_ENV:-}}"

if [ -z "$CAIRN_URL" ]; then
    echo ""
    echo -n "Cairn API URL [http://localhost:8000]: "
    read -r CAIRN_URL
    CAIRN_URL="${CAIRN_URL:-http://localhost:8000}"
fi

CAIRN_URL="${CAIRN_URL%/}"

# ──────────────────────────────────────────────
# Step 3: Test connectivity
# ──────────────────────────────────────────────

header "Testing connectivity..."

STATUS=$(curl -sf --max-time 5 "$CAIRN_URL/api/status" 2>/dev/null || echo "")
if [ -n "$STATUS" ]; then
    ok "Cairn is reachable at $CAIRN_URL"
    echo "    $(echo "$STATUS" | jq -r '"Memories: \(.memory_count // "?"), Projects: \(.project_count // "?")"' 2>/dev/null || echo "(status parsed)")"
else
    warn "Could not reach $CAIRN_URL/api/status"
    echo "  Cairn may not be running yet. Setup will continue."
    echo "  Make sure Cairn is running before starting a session."
fi

# ──────────────────────────────────────────────
# Step 4: Find hook scripts
# ──────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$REPO_DIR/examples/hooks"
ADAPTERS_DIR="$HOOKS_DIR/adapters"

if [ ! -f "$HOOKS_DIR/session-start.sh" ]; then
    fail "Could not find hook scripts at $HOOKS_DIR"
    echo "  Run this script from the cairn repo."
    exit 1
fi

# Ensure core hooks are executable
chmod +x "$HOOKS_DIR/session-start.sh" "$HOOKS_DIR/log-event.sh" "$HOOKS_DIR/session-end.sh"

# ──────────────────────────────────────────────
# Step 5: Detect installed IDEs
# ──────────────────────────────────────────────

header "Detecting installed IDEs..."

declare -A IDE_DETECTED
IDE_LIST=()

# Claude Code
if [ -d "$HOME/.claude" ]; then
    IDE_DETECTED[claude_code]=true
    IDE_LIST+=("claude_code")
    ok "Claude Code detected (~/.claude/)"
else
    IDE_DETECTED[claude_code]=false
    info "Claude Code not detected"
fi

# Cursor
if [ -d "$HOME/.cursor" ]; then
    IDE_DETECTED[cursor]=true
    IDE_LIST+=("cursor")
    ok "Cursor detected (~/.cursor/)"
else
    IDE_DETECTED[cursor]=false
    info "Cursor not detected"
fi

# Windsurf
if [ -d "$HOME/.codeium/windsurf" ] || [ -d "$HOME/.windsurf" ]; then
    IDE_DETECTED[windsurf]=true
    IDE_LIST+=("windsurf")
    ok "Windsurf detected"
else
    IDE_DETECTED[windsurf]=false
    info "Windsurf not detected"
fi

# Cline (VS Code extension)
CLINE_FOUND=false
for ext_dir in "$HOME/.vscode/extensions" "$HOME/.vscode-server/extensions"; do
    if [ -d "$ext_dir" ] && ls "$ext_dir" 2>/dev/null | grep -q "saoudrizwan.claude-dev"; then
        CLINE_FOUND=true
        break
    fi
done
if [ "$CLINE_FOUND" = true ]; then
    IDE_DETECTED[cline]=true
    IDE_LIST+=("cline")
    ok "Cline (VS Code) detected"
else
    IDE_DETECTED[cline]=false
    info "Cline not detected"
fi

# Continue
if [ -d "$HOME/.continue" ]; then
    IDE_DETECTED[continue]=true
    IDE_LIST+=("continue")
    ok "Continue detected (~/.continue/)"
else
    IDE_DETECTED[continue]=false
    info "Continue not detected"
fi

if [ ${#IDE_LIST[@]} -eq 0 ]; then
    warn "No supported IDEs detected."
    echo "  You can still configure manually — see the README for config locations."
    exit 0
fi

# ──────────────────────────────────────────────
# Step 6: Select IDEs to configure
# ──────────────────────────────────────────────

header "Select IDEs to configure"

declare -A IDE_NAMES
IDE_NAMES[claude_code]="Claude Code"
IDE_NAMES[cursor]="Cursor"
IDE_NAMES[windsurf]="Windsurf"
IDE_NAMES[cline]="Cline (VS Code)"
IDE_NAMES[continue]="Continue"

echo ""
echo "  Detected IDEs:"
for i in "${!IDE_LIST[@]}"; do
    echo "    $((i + 1)). ${IDE_NAMES[${IDE_LIST[$i]}]}"
done
echo "    a. All"
echo ""
echo -n "Configure which? [a]: "
read -r SELECTION
SELECTION="${SELECTION:-a}"

SELECTED_IDES=()
if [ "$SELECTION" = "a" ] || [ "$SELECTION" = "A" ]; then
    SELECTED_IDES=("${IDE_LIST[@]}")
else
    # Parse comma-separated or single number
    IFS=',' read -ra NUMS <<< "$SELECTION"
    for num in "${NUMS[@]}"; do
        num=$(echo "$num" | tr -d ' ')
        idx=$((num - 1))
        if [ "$idx" -ge 0 ] && [ "$idx" -lt "${#IDE_LIST[@]}" ]; then
            SELECTED_IDES+=("${IDE_LIST[$idx]}")
        fi
    done
fi

if [ ${#SELECTED_IDES[@]} -eq 0 ]; then
    fail "No valid selection. Exiting."
    exit 1
fi

# ──────────────────────────────────────────────
# Helper: merge cairn key into MCP config JSON
# ──────────────────────────────────────────────

MCP_ENTRY=$(jq -nc --arg url "$CAIRN_URL/mcp" '{
  cairn: { type: "http", url: $url }
}')

merge_mcp_config() {
    local config_file="$1"
    local config_dir
    config_dir=$(dirname "$config_file")

    if [ "$DRY_RUN" = true ]; then
        if [ -f "$config_file" ]; then
            info "Would merge cairn into $config_file"
            echo "    Existing mcpServers keys: $(jq -r '.mcpServers // {} | keys | join(", ")' "$config_file" 2>/dev/null || echo "none")"
        else
            info "Would create $config_file with:"
            echo "    $(jq -nc --argjson entry "$MCP_ENTRY" '{mcpServers: $entry}')"
        fi
        return 0
    fi

    mkdir -p "$config_dir"

    if [ -f "$config_file" ]; then
        # Check if cairn key already exists
        if jq -e '.mcpServers.cairn' "$config_file" &>/dev/null; then
            echo -n "    cairn already in $config_file — update? [y/N]: "
            read -r UPDATE
            if [[ ! "$UPDATE" =~ ^[Yy] ]]; then
                info "Skipped $config_file"
                return 0
            fi
        fi
        # Merge: add/update cairn key in mcpServers
        local tmp
        tmp=$(mktemp)
        jq --argjson entry "$MCP_ENTRY" '.mcpServers = ((.mcpServers // {}) + $entry)' "$config_file" > "$tmp"
        mv "$tmp" "$config_file"
    else
        jq -nc --argjson entry "$MCP_ENTRY" '{mcpServers: $entry}' > "$config_file"
    fi
    ok "MCP config written to $config_file"
}

# ──────────────────────────────────────────────
# Step 7: Configure each selected IDE
# ──────────────────────────────────────────────

for ide in "${SELECTED_IDES[@]}"; do
    header "Configuring ${IDE_NAMES[$ide]}..."

    case "$ide" in
        claude_code)
            # MCP config
            echo -n "  Configure MCP at project level (.mcp.json) or global (~/.claude)? [p/G]: "
            read -r SCOPE
            if [[ "$SCOPE" =~ ^[Pp] ]]; then
                merge_mcp_config ".mcp.json"
            else
                merge_mcp_config "$HOME/.claude/mcp.json"
            fi

            # Hooks
            echo -n "  Install session capture hooks? [Y/n]: "
            read -r INSTALL_HOOKS
            if [[ ! "$INSTALL_HOOKS" =~ ^[Nn] ]]; then
                SETTINGS_FILE="$HOME/.claude/settings.json"
                HOOK_CONFIG=$(jq -nc \
                    --arg start_cmd "CAIRN_URL=$CAIRN_URL $HOOKS_DIR/session-start.sh" \
                    --arg log_cmd "CAIRN_URL=$CAIRN_URL $HOOKS_DIR/log-event.sh" \
                    --arg end_cmd "CAIRN_URL=$CAIRN_URL $HOOKS_DIR/session-end.sh" \
                    '{
                        hooks: {
                            SessionStart: [{
                                matcher: "startup|resume",
                                hooks: [{ type: "command", command: $start_cmd, timeout: 15 }]
                            }],
                            PostToolUse: [{
                                matcher: "",
                                hooks: [{ type: "command", command: $log_cmd, timeout: 5 }]
                            }],
                            SessionEnd: [{
                                matcher: "",
                                hooks: [{ type: "command", command: $end_cmd, timeout: 30 }]
                            }]
                        }
                    }')

                if [ "$DRY_RUN" = true ]; then
                    info "Would merge hooks into $SETTINGS_FILE:"
                    echo "$HOOK_CONFIG" | jq .
                else
                    if [ -f "$SETTINGS_FILE" ]; then
                        local_tmp=$(mktemp)
                        jq --argjson hooks "$(echo "$HOOK_CONFIG" | jq '.hooks')" '.hooks = $hooks' "$SETTINGS_FILE" > "$local_tmp"
                        mv "$local_tmp" "$SETTINGS_FILE"
                    else
                        echo "$HOOK_CONFIG" | jq . > "$SETTINGS_FILE"
                    fi
                    ok "Hooks configured in $SETTINGS_FILE"
                fi
            fi
            CONFIGURED_IDES+=("Claude Code")
            ;;

        cursor)
            # MCP config
            merge_mcp_config ".cursor/mcp.json"

            # Hooks
            echo -n "  Install session capture hooks? [Y/n]: "
            read -r INSTALL_HOOKS
            if [[ ! "$INSTALL_HOOKS" =~ ^[Nn] ]]; then
                # Ensure adapters are executable
                chmod +x "$ADAPTERS_DIR/cursor/"*.sh 2>/dev/null || true

                HOOKS_CONFIG=$(jq -nc \
                    --arg start_cmd "CAIRN_URL=$CAIRN_URL $ADAPTERS_DIR/cursor/session-start.sh" \
                    --arg mcp_cmd "CAIRN_URL=$CAIRN_URL $ADAPTERS_DIR/cursor/after-mcp-execution.sh" \
                    --arg end_cmd "CAIRN_URL=$CAIRN_URL $ADAPTERS_DIR/cursor/session-end.sh" \
                    '{
                        hooks: {
                            "session-start": { command: $start_cmd, timeout: 15 },
                            "after-mcp-execution": { command: $mcp_cmd, timeout: 5 },
                            "session-end": { command: $end_cmd, timeout: 30 }
                        }
                    }')

                CURSOR_HOOKS_FILE=".cursor/hooks.json"
                if [ "$DRY_RUN" = true ]; then
                    info "Would write $CURSOR_HOOKS_FILE:"
                    echo "$HOOKS_CONFIG" | jq .
                else
                    mkdir -p .cursor
                    echo "$HOOKS_CONFIG" | jq . > "$CURSOR_HOOKS_FILE"
                    ok "Hooks configured in $CURSOR_HOOKS_FILE"
                fi
            fi
            CONFIGURED_IDES+=("Cursor")
            ;;

        windsurf)
            # MCP config
            if [ -d "$HOME/.codeium/windsurf" ]; then
                MCP_TARGET="$HOME/.codeium/windsurf/mcp.json"
            else
                MCP_TARGET=".windsurf/mcp.json"
            fi
            merge_mcp_config "$MCP_TARGET"

            # Hooks
            echo -n "  Install tool capture hook? (Windsurf has no session start/end hooks) [Y/n]: "
            read -r INSTALL_HOOKS
            if [[ ! "$INSTALL_HOOKS" =~ ^[Nn] ]]; then
                chmod +x "$ADAPTERS_DIR/windsurf/"*.sh 2>/dev/null || true

                HOOKS_CONFIG=$(jq -nc \
                    --arg cmd "CAIRN_URL=$CAIRN_URL $ADAPTERS_DIR/windsurf/post-mcp-tool-use.sh" \
                    '{
                        hooks: {
                            "post-mcp-tool-use": { command: $cmd, timeout: 10 }
                        }
                    }')

                if [ -d "$HOME/.codeium/windsurf" ]; then
                    WINDSURF_HOOKS_FILE="$HOME/.codeium/windsurf/hooks.json"
                else
                    WINDSURF_HOOKS_FILE=".windsurf/hooks.json"
                fi

                if [ "$DRY_RUN" = true ]; then
                    info "Would write $WINDSURF_HOOKS_FILE:"
                    echo "$HOOKS_CONFIG" | jq .
                else
                    mkdir -p "$(dirname "$WINDSURF_HOOKS_FILE")"
                    echo "$HOOKS_CONFIG" | jq . > "$WINDSURF_HOOKS_FILE"
                    ok "Hook configured in $WINDSURF_HOOKS_FILE"
                fi
                warn "Windsurf limitation: no session-end hook."
                echo "    The agent must call cairns(action=\"set\") directly, or run:"
                echo "    echo '{\"session_id\":\"SESSION_ID\"}' | $HOOKS_DIR/session-end.sh"
            fi
            CONFIGURED_IDES+=("Windsurf")
            ;;

        cline)
            # MCP: Cline manages MCP via its settings panel — print instructions
            echo ""
            info "Cline manages MCP servers via its settings panel."
            echo "    In VS Code, open Cline settings and add an MCP server:"
            echo "      Name: cairn"
            echo "      Type: http"
            echo "      URL:  $CAIRN_URL/mcp"
            echo ""

            # Hooks
            echo -n "  Install session capture hooks? [Y/n]: "
            read -r INSTALL_HOOKS
            if [[ ! "$INSTALL_HOOKS" =~ ^[Nn] ]]; then
                chmod +x "$ADAPTERS_DIR/cline/"* 2>/dev/null || true

                # Cline hooks go in the rules/hooks directory
                CLINE_HOOKS_DIR="$HOME/.cline/hooks"

                if [ "$DRY_RUN" = true ]; then
                    info "Would copy adapters to $CLINE_HOOKS_DIR/"
                    info "  TaskStart, PostToolUse, TaskCancel"
                else
                    mkdir -p "$CLINE_HOOKS_DIR"
                    for hook in TaskStart PostToolUse TaskCancel; do
                        cp "$ADAPTERS_DIR/cline/$hook" "$CLINE_HOOKS_DIR/$hook"
                        chmod +x "$CLINE_HOOKS_DIR/$hook"
                    done
                    # Write a config hint
                    cat > "$CLINE_HOOKS_DIR/README" <<HOOKEOF
# Cairn hooks for Cline
# These scripts are called by Cline's hook system.
# Set CAIRN_URL in your environment if not using localhost:8000.
# See: https://github.com/jasondostal/cairn-mcp/tree/main/examples/hooks/adapters/cline
HOOKEOF
                    ok "Hooks installed to $CLINE_HOOKS_DIR/"
                fi
            fi
            CONFIGURED_IDES+=("Cline")
            ;;

        continue)
            # Continue uses YAML — we print instructions instead of editing
            echo ""
            info "Continue uses YAML config. Add this to ~/.continue/config.yaml:"
            echo ""
            echo "    mcpServers:"
            echo "      - name: cairn"
            echo "        type: http"
            echo "        url: $CAIRN_URL/mcp"
            echo ""
            info "Continue does not support lifecycle hooks — use Tier 2 (agent calls cairns directly)."
            CONFIGURED_IDES+=("Continue")
            ;;
    esac
done

# ──────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────

echo ""
echo "========================================="
if [ "$DRY_RUN" = true ]; then
    echo "  Dry Run Complete"
else
    echo "  Setup Complete!"
fi
echo "========================================="
echo ""
echo "  Configured: ${CONFIGURED_IDES[*]}"
echo "  Cairn URL:  $CAIRN_URL"
echo ""
if [ "$DRY_RUN" = true ]; then
    echo "  Re-run without --dry-run to apply changes."
else
    echo "  Next steps:"
    echo "    1. Start (or restart) your IDE"
    echo "    2. Begin a session — Cairn should connect automatically"
    echo "    3. Check: curl -s $CAIRN_URL/api/status | jq ."
fi
echo ""
echo "  Documentation: $HOOKS_DIR/README.md"
echo ""
