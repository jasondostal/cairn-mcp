#!/usr/bin/env bash
# Shared helpers for Cairn setup scripts.
# Sourced by setup-env.sh and setup-auth.sh — not run directly.

# ──────────────────────────────────────────────
# Colors
# ──────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ──────────────────────────────────────────────
# Output helpers
# ──────────────────────────────────────────────

info()   { echo -e "${BLUE}[info]${NC} $*"; }
ok()     { echo -e "${GREEN}  [ok]${NC} $*"; }
warn()   { echo -e "${YELLOW}[warn]${NC} $*"; }
fail()   { echo -e "${RED}[fail]${NC} $*"; }
header() { echo -e "\n${BOLD}$*${NC}"; }

# ──────────────────────────────────────────────
# Interactive prompts
# ──────────────────────────────────────────────

# Prompt user for input, return default if non-interactive or empty
prompt() {
    local message="$1"
    local default="${2:-}"
    local result

    if [ "$NON_INTERACTIVE" = true ]; then
        echo "$default"
        return
    fi

    if [ -n "$default" ]; then
        echo -n "$message [$default]: " >&2
    else
        echo -n "$message: " >&2
    fi
    read -r result
    echo "${result:-$default}"
}

# Prompt for secret input (masked)
prompt_secret() {
    local message="$1"
    local default="${2:-}"
    local result

    if [ "$NON_INTERACTIVE" = true ]; then
        echo "$default"
        return
    fi

    if [ -n "$default" ]; then
        echo -n "$message [****]: " >&2
    else
        echo -n "$message: " >&2
    fi
    read -rs result
    echo "" >&2
    echo "${result:-$default}"
}

# Prompt for a numbered selection
prompt_select() {
    local message="$1"
    local default="$2"
    local result

    if [ "$NON_INTERACTIVE" = true ]; then
        echo "$default"
        return
    fi

    echo -n "$message [$default]: " >&2
    read -r result
    echo "${result:-$default}"
}

# Prompt yes/no, return 0 for yes, 1 for no
prompt_yn() {
    local message="$1"
    local default="${2:-n}"
    local result

    if [ "$NON_INTERACTIVE" = true ]; then
        [[ "$default" =~ ^[Yy] ]] && return 0 || return 1
    fi

    if [[ "$default" =~ ^[Yy] ]]; then
        echo -n "$message [Y/n]: " >&2
    else
        echo -n "$message [y/N]: " >&2
    fi
    read -r result
    result="${result:-$default}"
    [[ "$result" =~ ^[Yy] ]]
}

# ──────────────────────────────────────────────
# .env file manipulation
# ──────────────────────────────────────────────

# Set a key in the .env file (update if exists, append if not)
env_set() {
    local key="$1"
    local value="$2"
    local file="$3"

    if grep -q "^${key}=" "$file" 2>/dev/null; then
        local escaped_value
        escaped_value=$(printf '%s\n' "$value" | sed 's/[&/\]/\\&/g')
        sed -i "s|^${key}=.*|${key}=${escaped_value}|" "$file"
    elif grep -q "^# *${key}=" "$file" 2>/dev/null; then
        local escaped_value
        escaped_value=$(printf '%s\n' "$value" | sed 's/[&/\]/\\&/g')
        sed -i "s|^# *${key}=.*|${key}=${escaped_value}|" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
}

# Comment out a key in the .env file
env_comment() {
    local key="$1"
    local file="$2"

    if grep -q "^${key}=" "$file" 2>/dev/null; then
        sed -i "s|^${key}=|# ${key}=|" "$file"
    fi
}

# Ensure .env file exists (copy from .env.example or create empty)
env_ensure() {
    local env_file="$1"
    local project_dir="$2"

    if [ ! -f "$env_file" ]; then
        if [ -f "${project_dir}/.env.example" ]; then
            cp "${project_dir}/.env.example" "$env_file"
            ok "Created ${env_file} from .env.example"
        else
            touch "$env_file"
            ok "Created ${env_file}"
        fi
    fi
}

# ──────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────

# Mask a value for display (show first 4 chars, mask the rest)
mask_value() {
    local value="$1"
    if [ ${#value} -le 4 ]; then
        echo "****"
    else
        echo "${value:0:4}****"
    fi
}

# Generate a secure random secret
generate_secret() {
    if command -v openssl &>/dev/null; then
        openssl rand -base64 32
    elif command -v python3 &>/dev/null; then
        python3 -c "import secrets; print(secrets.token_urlsafe(32))"
    else
        fail "Neither openssl nor python3 found — cannot generate secret"
        exit 1
    fi
}
