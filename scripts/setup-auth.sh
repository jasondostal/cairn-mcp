#!/usr/bin/env bash
# Cairn Authentication Setup
# Interactive wizard for configuring auth mode, JWT secrets, OIDC providers,
# and writing .env configuration.
#
# Usage: ./scripts/setup-auth.sh [OPTIONS]
#
# Options:
#   --env-file PATH      Path to .env file (default: ./.env)
#   --dry-run            Show what would be written without writing
#   --non-interactive    Use env vars / defaults only (for CI)
#   --help               Show usage

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Defaults (can be overridden by flags)
ENV_FILE="${PROJECT_DIR}/.env"
DRY_RUN=false
NON_INTERACTIVE=false

# Source shared helpers
# shellcheck source=setup-lib.sh
source "${SCRIPT_DIR}/setup-lib.sh"

# ──────────────────────────────────────────────
# Parse arguments
# ──────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-file)    ENV_FILE="$2"; shift 2 ;;
        --dry-run)     DRY_RUN=true; shift ;;
        --non-interactive) NON_INTERACTIVE=true; shift ;;
        --help|-h)
            head -12 "$0" | tail -10 | sed 's/^# \?//'
            exit 0
            ;;
        *)
            fail "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ──────────────────────────────────────────────
# Auth config values (populated during wizard)
# ──────────────────────────────────────────────

AUTH_ENABLED=false
JWT_SECRET=""
JWT_EXPIRE_MINUTES="1440"
API_KEY=""
OIDC_ENABLED=false
OIDC_PROVIDER_URL=""
OIDC_CLIENT_ID=""
OIDC_CLIENT_SECRET=""
OIDC_SCOPES="openid email profile"
OIDC_DEFAULT_ROLE="user"
OIDC_ADMIN_GROUPS=""
PUBLIC_URL=""
STDIO_USER=""
AUTH_MODE=1
OIDC_PROVIDER_NAME=""

# ──────────────────────────────────────────────
# Banner
# ──────────────────────────────────────────────

echo ""
echo -e "${BOLD}Cairn Authentication Setup${NC}"
echo "══════════════════════════"
echo ""

if [ "$DRY_RUN" = true ]; then
    warn "DRY RUN — no files will be written"
    echo ""
fi

if [ "$NON_INTERACTIVE" = true ]; then
    info "Non-interactive mode — using env vars and defaults"
    echo ""
fi

# ──────────────────────────────────────────────
# Step 1: Auth mode selection
# ──────────────────────────────────────────────

header "Choose an authentication mode:"
echo ""
echo "  1) None          — No authentication (local dev, single user)"
echo "  2) Local auth    — Username/password with JWT tokens"
echo "  3) Local + OIDC  — Single sign-on with an identity provider"
echo ""

AUTH_MODE=$(prompt_select "Selection" "1")

case "$AUTH_MODE" in
    1)
        AUTH_ENABLED=false
        OIDC_ENABLED=false
        ;;
    2)
        AUTH_ENABLED=true
        OIDC_ENABLED=false
        ;;
    3)
        AUTH_ENABLED=true
        OIDC_ENABLED=true
        ;;
    *)
        fail "Invalid selection: $AUTH_MODE"
        exit 1
        ;;
esac

# Mode 1: no auth — skip to writing
if [ "$AUTH_MODE" = "1" ]; then
    ok "Auth disabled — no further configuration needed"
fi

# ──────────────────────────────────────────────
# Step 2: JWT secret (modes 2 & 3)
# ──────────────────────────────────────────────

if [ "$AUTH_ENABLED" = true ]; then
    header "JWT Configuration"
    echo -e "─────────────────"
    echo ""

    echo -n "Generating JWT signing secret... "
    JWT_SECRET=$(generate_secret)
    echo "done."
    echo ""
    echo -e "  Generated: ${DIM}${JWT_SECRET}${NC}"
    echo ""

    CUSTOM_SECRET=$(prompt "Use this secret, or paste your own (Enter to accept)" "")
    if [ -n "$CUSTOM_SECRET" ]; then
        JWT_SECRET="$CUSTOM_SECRET"
    fi

    JWT_EXPIRE_MINUTES=$(prompt "JWT token lifetime in minutes" "1440")
    echo ""
fi

# ──────────────────────────────────────────────
# Step 3: Static API key (optional, modes 2 & 3)
# ──────────────────────────────────────────────

if [ "$AUTH_ENABLED" = true ]; then
    header "Static API Key (optional)"
    echo -e "─────────────────────────"
    echo ""
    echo "A static API key provides simple shared-secret auth for the REST API."
    echo "Leave blank to skip (JWT/PAT auth is sufficient for most setups)."
    echo ""

    API_KEY=$(prompt_secret "API key" "")
fi

# ──────────────────────────────────────────────
# Step 4: OIDC configuration (mode 3 only)
# ──────────────────────────────────────────────

if [ "$OIDC_ENABLED" = true ]; then
    header "OIDC / SSO Configuration"
    echo -e "─────────────────────────"
    echo ""
    echo "Provider:"
    echo "  1) Authentik"
    echo "  2) Keycloak"
    echo "  3) Auth0"
    echo "  4) Okta"
    echo "  5) Azure AD"
    echo "  6) Other (generic OIDC)"
    echo ""

    PROVIDER_NUM=$(prompt_select "Selection" "6")

    local_hint=""
    case "$PROVIDER_NUM" in
        1) OIDC_PROVIDER_NAME="Authentik";  local_hint="https://auth.example.com/application/o/<app-slug>/" ;;
        2) OIDC_PROVIDER_NAME="Keycloak";   local_hint="https://keycloak.example.com/realms/<realm>/" ;;
        3) OIDC_PROVIDER_NAME="Auth0";      local_hint="https://<tenant>.auth0.com/" ;;
        4) OIDC_PROVIDER_NAME="Okta";       local_hint="https://<org>.okta.com/" ;;
        5) OIDC_PROVIDER_NAME="Azure AD";   local_hint="https://login.microsoftonline.com/<tenant-id>/v2.0" ;;
        6) OIDC_PROVIDER_NAME="Generic OIDC"; local_hint="" ;;
        *) OIDC_PROVIDER_NAME="Generic OIDC"; local_hint="" ;;
    esac

    echo ""
    if [ -n "$local_hint" ]; then
        echo -e "  ${DIM}Expected format: ${local_hint}${NC}"
    fi

    OIDC_PROVIDER_URL=$(prompt "Provider URL" "")

    if [ -z "$OIDC_PROVIDER_URL" ]; then
        fail "Provider URL is required for OIDC"
        exit 1
    fi

    # Strip trailing slash for discovery URL construction, then re-add
    OIDC_PROVIDER_URL="${OIDC_PROVIDER_URL%/}"

    # Validate OIDC discovery endpoint
    echo ""
    echo -n "Validating OIDC discovery endpoint... "
    DISCOVERY_URL="${OIDC_PROVIDER_URL}/.well-known/openid-configuration"

    if command -v curl &>/dev/null; then
        DISCOVERY_RESPONSE=$(curl -sf --max-time 10 "$DISCOVERY_URL" 2>/dev/null || echo "")

        if [ -n "$DISCOVERY_RESPONSE" ]; then
            HAS_AUTH=$(echo "$DISCOVERY_RESPONSE" | grep -c "authorization_endpoint" || true)
            HAS_TOKEN=$(echo "$DISCOVERY_RESPONSE" | grep -c "token_endpoint" || true)

            if [ "$HAS_AUTH" -gt 0 ] && [ "$HAS_TOKEN" -gt 0 ]; then
                echo ""
                ok "Found: ${DISCOVERY_URL}"
            else
                echo ""
                warn "Endpoint returned JSON but missing authorization_endpoint or token_endpoint"
                echo "  You may want to verify the provider URL."
            fi
        else
            echo ""
            warn "Could not reach ${DISCOVERY_URL}"
            echo "  The provider may not be running, or the URL may be incorrect."
            echo "  Setup will continue — verify the URL before starting Cairn."
        fi
    else
        echo "skipped (curl not available)"
    fi

    # Re-add trailing slash for storage consistency
    OIDC_PROVIDER_URL="${OIDC_PROVIDER_URL}/"

    echo ""
    OIDC_CLIENT_ID=$(prompt "Client ID" "")
    if [ -z "$OIDC_CLIENT_ID" ]; then
        fail "Client ID is required for OIDC"
        exit 1
    fi

    OIDC_CLIENT_SECRET=$(prompt_secret "Client Secret" "")
    if [ -z "$OIDC_CLIENT_SECRET" ]; then
        fail "Client Secret is required for OIDC"
        exit 1
    fi

    echo ""
    OIDC_SCOPES=$(prompt "Scopes" "openid email profile")
    OIDC_DEFAULT_ROLE=$(prompt "Default role for new OIDC users" "user")
    OIDC_ADMIN_GROUPS=$(prompt "Admin groups (comma-separated, users in these groups get admin role)" "")

    echo ""
    echo "Public URL (required if Cairn is behind a reverse proxy):"
    echo "  This is the URL users access in their browser, e.g. https://cairn.example.com"
    if [ -n "$PUBLIC_URL" ]; then
        echo "  Callback URL will be: ${PUBLIC_URL}/api/auth/oidc/callback"
    fi
    echo ""
    PUBLIC_URL=$(prompt "Public URL" "")

    if [ -n "$PUBLIC_URL" ]; then
        PUBLIC_URL="${PUBLIC_URL%/}"
        echo -e "  Callback URL: ${DIM}${PUBLIC_URL}/api/auth/oidc/callback${NC}"
    fi
fi

# ──────────────────────────────────────────────
# Step 5: Stdio identity (optional)
# ──────────────────────────────────────────────

if [ "$AUTH_ENABLED" = true ]; then
    header "MCP Stdio Identity (optional)"
    echo -e "─────────────────────────────"
    echo ""
    echo "If you run Cairn via stdio transport (not HTTP), specify a username"
    echo "to map stdio sessions to. Leave blank if using HTTP only."
    echo ""
    STDIO_USER=$(prompt "Stdio user" "")
fi

# ──────────────────────────────────────────────
# Step 6: Write .env
# ──────────────────────────────────────────────

header "Writing configuration..."
echo ""

# Build a display of what will be written
declare -a CONFIG_LINES=()
CONFIG_LINES+=("CAIRN_AUTH_ENABLED=${AUTH_ENABLED}")

if [ "$AUTH_ENABLED" = true ]; then
    CONFIG_LINES+=("CAIRN_AUTH_JWT_SECRET=$(mask_value "$JWT_SECRET")")
    CONFIG_LINES+=("CAIRN_AUTH_JWT_EXPIRE_MINUTES=${JWT_EXPIRE_MINUTES}")

    if [ -n "$API_KEY" ]; then
        CONFIG_LINES+=("CAIRN_API_KEY=$(mask_value "$API_KEY")")
    fi

    if [ "$OIDC_ENABLED" = true ]; then
        CONFIG_LINES+=("CAIRN_OIDC_ENABLED=true")
        CONFIG_LINES+=("CAIRN_OIDC_PROVIDER_URL=${OIDC_PROVIDER_URL}")
        CONFIG_LINES+=("CAIRN_OIDC_CLIENT_ID=$(mask_value "$OIDC_CLIENT_ID")")
        CONFIG_LINES+=("CAIRN_OIDC_CLIENT_SECRET=$(mask_value "$OIDC_CLIENT_SECRET")")
        CONFIG_LINES+=("CAIRN_OIDC_SCOPES=${OIDC_SCOPES}")
        CONFIG_LINES+=("CAIRN_OIDC_DEFAULT_ROLE=${OIDC_DEFAULT_ROLE}")
        if [ -n "$OIDC_ADMIN_GROUPS" ]; then
            CONFIG_LINES+=("CAIRN_OIDC_ADMIN_GROUPS=${OIDC_ADMIN_GROUPS}")
        fi
        if [ -n "$PUBLIC_URL" ]; then
            CONFIG_LINES+=("CAIRN_PUBLIC_URL=${PUBLIC_URL}")
        fi
    else
        CONFIG_LINES+=("CAIRN_OIDC_ENABLED=false")
    fi

    if [ -n "$STDIO_USER" ]; then
        CONFIG_LINES+=("CAIRN_STDIO_USER=${STDIO_USER}")
    fi
fi

for line in "${CONFIG_LINES[@]}"; do
    echo "  ${line}"
done
echo ""

if [ "$DRY_RUN" = true ]; then
    info "Would write to ${ENV_FILE}"
    echo ""
else
    env_ensure "$ENV_FILE" "$PROJECT_DIR"

    # Write auth settings
    env_set "CAIRN_AUTH_ENABLED" "$AUTH_ENABLED" "$ENV_FILE"
    env_set "CAIRN_AUTH_JWT_SECRET" "$JWT_SECRET" "$ENV_FILE"

    if [ "$AUTH_ENABLED" = true ]; then
        env_set "CAIRN_AUTH_JWT_EXPIRE_MINUTES" "$JWT_EXPIRE_MINUTES" "$ENV_FILE"

        if [ -n "$API_KEY" ]; then
            env_set "CAIRN_API_KEY" "$API_KEY" "$ENV_FILE"
        fi
    fi

    # OIDC settings
    if [ "$OIDC_ENABLED" = true ]; then
        env_set "CAIRN_OIDC_ENABLED" "true" "$ENV_FILE"
        env_set "CAIRN_OIDC_PROVIDER_URL" "$OIDC_PROVIDER_URL" "$ENV_FILE"
        env_set "CAIRN_OIDC_CLIENT_ID" "$OIDC_CLIENT_ID" "$ENV_FILE"
        env_set "CAIRN_OIDC_CLIENT_SECRET" "$OIDC_CLIENT_SECRET" "$ENV_FILE"
        env_set "CAIRN_OIDC_SCOPES" "$OIDC_SCOPES" "$ENV_FILE"
        env_set "CAIRN_OIDC_DEFAULT_ROLE" "$OIDC_DEFAULT_ROLE" "$ENV_FILE"
        if [ -n "$OIDC_ADMIN_GROUPS" ]; then
            env_set "CAIRN_OIDC_ADMIN_GROUPS" "$OIDC_ADMIN_GROUPS" "$ENV_FILE"
        fi
        if [ -n "$PUBLIC_URL" ]; then
            env_set "CAIRN_PUBLIC_URL" "$PUBLIC_URL" "$ENV_FILE"
        fi
    else
        env_comment "CAIRN_OIDC_ENABLED" "$ENV_FILE"
        env_comment "CAIRN_OIDC_PROVIDER_URL" "$ENV_FILE"
        env_comment "CAIRN_OIDC_CLIENT_ID" "$ENV_FILE"
        env_comment "CAIRN_OIDC_CLIENT_SECRET" "$ENV_FILE"
    fi

    # Stdio user
    if [ -n "$STDIO_USER" ]; then
        env_set "CAIRN_STDIO_USER" "$STDIO_USER" "$ENV_FILE"
    fi

    ok "Written to ${ENV_FILE}"
fi

# ──────────────────────────────────────────────
# Step 7: Test (if cairn is running)
# ──────────────────────────────────────────────

header "Testing configuration..."
echo ""

CAIRN_URL="${CAIRN_URL:-}"
CAIRN_PORT="${CAIRN_PORT:-}"
if [ -z "$CAIRN_URL" ] && [ -f "$ENV_FILE" ]; then
    CAIRN_PORT=$(grep "^CAIRN_HTTP_PORT=" "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
fi
CAIRN_PORT="${CAIRN_PORT:-8000}"
CAIRN_URL="${CAIRN_URL:-http://localhost:${CAIRN_PORT}}"

UI_URL="http://localhost:3000"

CAIRN_RUNNING=false
if command -v curl &>/dev/null; then
    STATUS_RESPONSE=$(curl -sf --max-time 5 "${CAIRN_URL}/api/status" 2>/dev/null || echo "")
    if [ -n "$STATUS_RESPONSE" ]; then
        CAIRN_RUNNING=true
        ok "Cairn is running (${CAIRN_URL})"

        if [ "$AUTH_ENABLED" = true ]; then
            ok "Auth enabled"
        else
            ok "Auth disabled"
        fi

        if [ "$OIDC_ENABLED" = true ]; then
            ok "OIDC provider configured"
        fi

        USER_COUNT=$(echo "$STATUS_RESPONSE" | grep -o '"user_count":[0-9]*' | cut -d: -f2 || echo "")
        if [ "$USER_COUNT" = "0" ] || [ -z "$USER_COUNT" ]; then
            ok "No users yet — visit ${UI_URL}/login to create admin"
        fi
    fi
fi

DISPLAY_URL="${PUBLIC_URL:-$CAIRN_URL}"

if [ "$CAIRN_RUNNING" = true ]; then
    echo ""
    if [ "$AUTH_ENABLED" = true ]; then
        echo "  MCP config snippet (with auth):"
        echo ""
        echo "    {"
        echo "      \"mcpServers\": {"
        echo "        \"cairn\": {"
        echo "          \"url\": \"${DISPLAY_URL}/mcp\","
        echo "          \"headers\": {"
        echo "            \"Authorization\": \"Bearer <your-token>\""
        echo "          }"
        echo "        }"
        echo "      }"
        echo "    }"
        echo ""
        echo "  Create a PAT at ${DISPLAY_URL}/settings for machine clients."
    else
        echo "  MCP config snippet:"
        echo ""
        echo "    {"
        echo "      \"mcpServers\": {"
        echo "        \"cairn\": {"
        echo "          \"url\": \"${DISPLAY_URL}/mcp\""
        echo "        }"
        echo "      }"
        echo "    }"
    fi
else
    echo "Next steps:"
    echo "  1. docker compose up -d"
    echo "  2. Visit ${UI_URL}/login to create your admin account"
    if [ "$AUTH_ENABLED" = true ]; then
        echo "  3. Create a PAT at /settings for MCP client auth"
    fi
fi

# ──────────────────────────────────────────────
# Step 8: Summary
# ──────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════"

MODE_LABEL="None"
if [ "$AUTH_MODE" = "2" ]; then
    MODE_LABEL="Local auth (JWT)"
elif [ "$AUTH_MODE" = "3" ]; then
    if [ -n "$OIDC_PROVIDER_NAME" ]; then
        MODE_LABEL="OIDC (${OIDC_PROVIDER_NAME})"
    else
        MODE_LABEL="OIDC"
    fi
fi

echo "  Auth mode:     ${MODE_LABEL}"

if [ "$AUTH_ENABLED" = true ]; then
    echo "  JWT secret:    configured"
fi

if [ "$OIDC_ENABLED" = true ]; then
    echo "  OIDC provider: ${OIDC_PROVIDER_URL}"
    if [ -n "$PUBLIC_URL" ]; then
        echo "  Public URL:    ${PUBLIC_URL}"
        echo "  Callback URL:  ${PUBLIC_URL}/api/auth/oidc/callback"
    fi
fi

if [ "$DRY_RUN" = true ]; then
    echo "  Config file:   ${ENV_FILE} (dry run — not written)"
else
    echo "  Config file:   ${ENV_FILE} (updated)"
fi

echo "═══════════════════════════════════════"
echo ""
echo "  Docs: https://github.com/jasondostal/cairn-mcp/blob/main/docs/authentication.md"
echo ""
