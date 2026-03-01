#!/usr/bin/env bash
# Cairn Environment Setup
# Interactive wizard for configuring .env: profile selection, LLM backend,
# database, embeddings, and knowledge graph.
#
# Usage: ./scripts/setup-env.sh [OPTIONS]
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
            head -13 "$0" | tail -11 | sed 's/^# \?//'
            exit 0
            ;;
        *)
            fail "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ──────────────────────────────────────────────
# Config values (populated during wizard)
# ──────────────────────────────────────────────

PROFILE=""
PROFILE_NUM=1
DB_PASS="cairn-dev-password"
LLM_BACKEND="ollama"
LLM_PROVIDER_NUM=4

# Ollama
OLLAMA_URL="http://localhost:11434"
OLLAMA_MODEL="qwen2.5-coder:7b"

# Bedrock
BEDROCK_MODEL="us.meta.llama3-2-90b-instruct-v1:0"
BEDROCK_REGION="us-east-1"
AWS_KEY=""
AWS_SECRET=""

# OpenAI
OPENAI_KEY=""
OPENAI_BASE_URL="https://api.openai.com"
OPENAI_MODEL="gpt-4o-mini"

# Gemini
GEMINI_KEY=""
GEMINI_MODEL="gemini-2.0-flash"

# Embedding
EMBEDDING_BACKEND="local"
EMBEDDING_MODEL="all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS="384"

# Graph
GRAPH_ENABLED=false

# ──────────────────────────────────────────────
# Banner
# ──────────────────────────────────────────────

echo ""
echo -e "${BOLD}Cairn Environment Setup${NC}"
echo "═══════════════════════"
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
# Step 1: Profile selection
# ──────────────────────────────────────────────

header "How do you want to run Cairn?"
echo ""
echo "  1) Local dev      — Ollama, local embeddings, no graph."
echo "                      Free, runs entirely on your machine."
echo ""
echo "  2) Recommended    — Cloud LLM, knowledge graph, enhanced search."
echo "                      Best experience. Requires an API key."
echo ""
echo "  3) Enterprise     — Everything in Recommended plus audit trail,"
echo "                      webhooks, alerting, and data retention."
echo ""
echo "  4) Custom         — Choose every setting yourself."
echo ""

PROFILE_NUM=$(prompt_select "Selection" "1")

case "$PROFILE_NUM" in
    1) PROFILE="enriched" ;;
    2) PROFILE="knowledge"; GRAPH_ENABLED=true ;;
    3) PROFILE="enterprise"; GRAPH_ENABLED=true ;;
    4) PROFILE="" ;;
    *)
        fail "Invalid selection: $PROFILE_NUM"
        exit 1
        ;;
esac

# ──────────────────────────────────────────────
# Step 2: Database password
# ──────────────────────────────────────────────

header "Database Configuration"
echo -e "──────────────────────"
echo ""
echo "The default password is for local development only."
echo "Change it if Cairn will be network-accessible."
echo ""

DB_PASS=$(prompt_secret "Database password" "cairn-dev-password")

# ──────────────────────────────────────────────
# Step 3: LLM backend
# ──────────────────────────────────────────────

header "LLM Backend"
echo -e "────────────"
echo ""

if [ "$PROFILE_NUM" = "1" ]; then
    # Local dev: Ollama is the default
    echo "Using Ollama (local, free). Make sure Ollama is running."
    echo ""

    OLLAMA_URL=$(prompt "Ollama URL" "http://localhost:11434")
    OLLAMA_MODEL=$(prompt "Model" "qwen2.5-coder:7b")
    LLM_BACKEND="ollama"

    # Validate Ollama is reachable
    echo ""
    echo -n "Checking Ollama... "
    if command -v curl &>/dev/null; then
        OLLAMA_RESPONSE=$(curl -sf --max-time 5 "${OLLAMA_URL}/api/tags" 2>/dev/null || echo "")
        if [ -n "$OLLAMA_RESPONSE" ]; then
            echo ""
            ok "Ollama is running at ${OLLAMA_URL}"
        else
            echo ""
            warn "Could not reach Ollama at ${OLLAMA_URL}"
            echo "  Make sure Ollama is running before starting Cairn."
            echo "  Install: https://ollama.com"
        fi
    else
        echo "skipped (curl not available)"
    fi

elif [ "$PROFILE_NUM" = "4" ]; then
    # Custom: full provider selection
    echo "Choose your LLM provider:"
    echo ""
    echo "  1) AWS Bedrock    — Llama, Claude, Mistral via AWS"
    echo "  2) OpenAI         — GPT-4o, GPT-4o-mini (or any compatible API)"
    echo "  3) Google Gemini  — Gemini 2.0 Flash (free tier available)"
    echo "  4) Ollama         — Local models (free, no API key)"
    echo ""

    LLM_PROVIDER_NUM=$(prompt_select "Selection" "4")

else
    # Recommended / Enterprise: cloud LLM selection
    echo "Choose your LLM provider:"
    echo ""
    echo "  1) AWS Bedrock    — Llama, Claude, Mistral via AWS"
    echo "  2) OpenAI         — GPT-4o, GPT-4o-mini (or any compatible API)"
    echo "  3) Google Gemini  — Gemini 2.0 Flash (free tier available)"
    echo "  4) Ollama         — Local models (free, no API key)"
    echo ""

    LLM_PROVIDER_NUM=$(prompt_select "Selection" "1")
fi

# Collect provider-specific credentials
if [ "$PROFILE_NUM" != "1" ]; then
    case "$LLM_PROVIDER_NUM" in
        1)
            LLM_BACKEND="bedrock"
            echo ""
            header "AWS Bedrock Configuration"
            echo -e "─────────────────────────"
            echo ""
            BEDROCK_MODEL=$(prompt "Model" "us.meta.llama3-2-90b-instruct-v1:0")
            BEDROCK_REGION=$(prompt "Region" "us-east-1")
            AWS_KEY=$(prompt_secret "Access Key ID" "")
            AWS_SECRET=$(prompt_secret "Secret Access Key" "")

            if [ -z "$AWS_KEY" ] || [ -z "$AWS_SECRET" ]; then
                warn "AWS credentials are required for Bedrock."
                echo "  You can also set them in ~/.aws/credentials."
            fi
            ;;
        2)
            LLM_BACKEND="openai"
            echo ""
            header "OpenAI Configuration"
            echo -e "────────────────────"
            echo ""
            OPENAI_KEY=$(prompt_secret "API Key" "")
            OPENAI_BASE_URL=$(prompt "Base URL" "https://api.openai.com")
            OPENAI_MODEL=$(prompt "Model" "gpt-4o-mini")
            echo ""
            echo -e "  ${DIM}Tip: Works with any OpenAI-compatible API — Groq, Together,${NC}"
            echo -e "  ${DIM}Mistral, LM Studio, vLLM. Just change the base URL.${NC}"
            ;;
        3)
            LLM_BACKEND="gemini"
            echo ""
            header "Google Gemini Configuration"
            echo -e "───────────────────────────"
            echo ""
            GEMINI_KEY=$(prompt_secret "API Key" "")
            GEMINI_MODEL=$(prompt "Model" "gemini-2.0-flash")
            ;;
        4)
            LLM_BACKEND="ollama"
            echo ""
            OLLAMA_URL=$(prompt "Ollama URL" "http://localhost:11434")
            OLLAMA_MODEL=$(prompt "Model" "qwen2.5-coder:7b")
            ;;
        *)
            fail "Invalid selection: $LLM_PROVIDER_NUM"
            exit 1
            ;;
    esac
fi

# ──────────────────────────────────────────────
# Step 4: Embedding backend
# ──────────────────────────────────────────────

if [ "$PROFILE_NUM" = "1" ]; then
    # Local dev: always local embeddings
    echo ""
    ok "Embeddings: local (all-MiniLM-L6-v2, 384 dimensions)"
    EMBEDDING_BACKEND="local"

elif [ "$LLM_BACKEND" = "bedrock" ]; then
    echo ""
    header "Embedding Backend"
    echo -e "─────────────────"
    echo ""
    echo "  1) Local          — all-MiniLM-L6-v2 (384-dim, runs in container)"
    echo "  2) AWS Bedrock    — Titan V2 (1024-dim, uses same AWS credentials)"
    echo ""

    EMB_NUM=$(prompt_select "Selection" "1")
    if [ "$EMB_NUM" = "2" ]; then
        EMBEDDING_BACKEND="bedrock"
        EMBEDDING_DIMENSIONS=$(prompt "Embedding dimensions (256, 512, 1024)" "1024")
        EMBEDDING_MODEL=""
    else
        EMBEDDING_BACKEND="local"
    fi

elif [ "$LLM_BACKEND" = "openai" ]; then
    echo ""
    header "Embedding Backend"
    echo -e "─────────────────"
    echo ""
    echo "  1) Local          — all-MiniLM-L6-v2 (384-dim, runs in container)"
    echo "  2) OpenAI         — text-embedding-3-small (uses same API key)"
    echo ""

    EMB_NUM=$(prompt_select "Selection" "1")
    if [ "$EMB_NUM" = "2" ]; then
        EMBEDDING_BACKEND="openai"
        EMBEDDING_MODEL="text-embedding-3-small"
        EMBEDDING_DIMENSIONS="1536"
    else
        EMBEDDING_BACKEND="local"
    fi

else
    # Gemini or Ollama LLM: default to local embeddings
    echo ""
    ok "Embeddings: local (all-MiniLM-L6-v2, 384 dimensions)"
    EMBEDDING_BACKEND="local"
fi

# ──────────────────────────────────────────────
# Step 5: Knowledge graph (custom tier only — others pre-set)
# ──────────────────────────────────────────────

if [ "$PROFILE_NUM" = "2" ] || [ "$PROFILE_NUM" = "3" ]; then
    echo ""
    header "Knowledge Graph"
    echo -e "───────────────"
    echo ""
    echo "  Neo4j enabled — entities and relationships will be extracted"
    echo "  from stored memories and connected in a knowledge graph."
    echo "  Neo4j runs as a Docker container alongside Cairn."
    GRAPH_ENABLED=true

elif [ "$PROFILE_NUM" = "4" ]; then
    echo ""
    header "Knowledge Graph"
    echo -e "───────────────"
    echo ""
    echo "Neo4j enables entity extraction and a knowledge graph that connects"
    echo "memories through shared people, places, projects, and concepts."
    echo ""

    if prompt_yn "Enable knowledge graph (Neo4j)?" "n"; then
        GRAPH_ENABLED=true
        ok "Knowledge graph enabled"
    else
        GRAPH_ENABLED=false
        ok "Knowledge graph disabled (can enable later via settings)"
    fi
fi

# ──────────────────────────────────────────────
# Custom tier: additional settings
# ──────────────────────────────────────────────

ENRICHMENT_ENABLED="true"
RERANKING_ENABLED="false"
CORS_ORIGINS="*"

if [ "$PROFILE_NUM" = "4" ]; then
    echo ""
    header "Additional Settings"
    echo -e "───────────────────"
    echo ""

    if prompt_yn "Enable LLM enrichment (summaries, tags, importance scoring)?" "y"; then
        ENRICHMENT_ENABLED="true"
    else
        ENRICHMENT_ENABLED="false"
    fi

    if prompt_yn "Enable cross-encoder reranking (improves search quality)?" "n"; then
        RERANKING_ENABLED="true"
    else
        RERANKING_ENABLED="false"
    fi

    echo ""
    CORS_ORIGINS=$(prompt "CORS origins (* for all, or comma-separated URLs)" "*")
fi

# ──────────────────────────────────────────────
# Step 6: Write .env
# ──────────────────────────────────────────────

header "Writing configuration..."
echo ""

# Build display of what will be written
declare -a CONFIG_LINES=()

if [ -n "$PROFILE" ]; then
    CONFIG_LINES+=("CAIRN_PROFILE=${PROFILE}")
fi

CONFIG_LINES+=("CAIRN_DB_PASS=$(mask_value "$DB_PASS")")
CONFIG_LINES+=("CAIRN_LLM_BACKEND=${LLM_BACKEND}")

case "$LLM_BACKEND" in
    ollama)
        CONFIG_LINES+=("CAIRN_OLLAMA_URL=${OLLAMA_URL}")
        CONFIG_LINES+=("CAIRN_OLLAMA_MODEL=${OLLAMA_MODEL}")
        ;;
    bedrock)
        CONFIG_LINES+=("CAIRN_BEDROCK_MODEL=${BEDROCK_MODEL}")
        CONFIG_LINES+=("AWS_DEFAULT_REGION=${BEDROCK_REGION}")
        [ -n "$AWS_KEY" ] && CONFIG_LINES+=("AWS_ACCESS_KEY_ID=$(mask_value "$AWS_KEY")")
        [ -n "$AWS_SECRET" ] && CONFIG_LINES+=("AWS_SECRET_ACCESS_KEY=$(mask_value "$AWS_SECRET")")
        ;;
    openai)
        [ -n "$OPENAI_KEY" ] && CONFIG_LINES+=("CAIRN_OPENAI_API_KEY=$(mask_value "$OPENAI_KEY")")
        CONFIG_LINES+=("CAIRN_OPENAI_BASE_URL=${OPENAI_BASE_URL}")
        CONFIG_LINES+=("CAIRN_OPENAI_MODEL=${OPENAI_MODEL}")
        ;;
    gemini)
        [ -n "$GEMINI_KEY" ] && CONFIG_LINES+=("CAIRN_GEMINI_API_KEY=$(mask_value "$GEMINI_KEY")")
        CONFIG_LINES+=("CAIRN_GEMINI_MODEL=${GEMINI_MODEL}")
        ;;
esac

CONFIG_LINES+=("CAIRN_EMBEDDING_BACKEND=${EMBEDDING_BACKEND}")
if [ "$EMBEDDING_BACKEND" != "local" ]; then
    CONFIG_LINES+=("CAIRN_EMBEDDING_DIMENSIONS=${EMBEDDING_DIMENSIONS}")
fi

if [ "$GRAPH_ENABLED" = true ]; then
    CONFIG_LINES+=("CAIRN_GRAPH_BACKEND=neo4j")
    CONFIG_LINES+=("CAIRN_KNOWLEDGE_EXTRACTION=true")
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

    # Profile
    if [ -n "$PROFILE" ]; then
        env_set "CAIRN_PROFILE" "$PROFILE" "$ENV_FILE"
    fi

    # Database
    env_set "CAIRN_DB_PASS" "$DB_PASS" "$ENV_FILE"

    # LLM backend
    env_set "CAIRN_LLM_BACKEND" "$LLM_BACKEND" "$ENV_FILE"

    case "$LLM_BACKEND" in
        ollama)
            env_set "CAIRN_OLLAMA_URL" "$OLLAMA_URL" "$ENV_FILE"
            env_set "CAIRN_OLLAMA_MODEL" "$OLLAMA_MODEL" "$ENV_FILE"
            # Comment out other backends
            env_comment "CAIRN_BEDROCK_MODEL" "$ENV_FILE"
            env_comment "CAIRN_OPENAI_API_KEY" "$ENV_FILE"
            env_comment "CAIRN_GEMINI_API_KEY" "$ENV_FILE"
            ;;
        bedrock)
            env_set "CAIRN_BEDROCK_MODEL" "$BEDROCK_MODEL" "$ENV_FILE"
            env_set "AWS_DEFAULT_REGION" "$BEDROCK_REGION" "$ENV_FILE"
            [ -n "$AWS_KEY" ] && env_set "AWS_ACCESS_KEY_ID" "$AWS_KEY" "$ENV_FILE"
            [ -n "$AWS_SECRET" ] && env_set "AWS_SECRET_ACCESS_KEY" "$AWS_SECRET" "$ENV_FILE"
            env_comment "CAIRN_OPENAI_API_KEY" "$ENV_FILE"
            env_comment "CAIRN_GEMINI_API_KEY" "$ENV_FILE"
            ;;
        openai)
            [ -n "$OPENAI_KEY" ] && env_set "CAIRN_OPENAI_API_KEY" "$OPENAI_KEY" "$ENV_FILE"
            env_set "CAIRN_OPENAI_BASE_URL" "$OPENAI_BASE_URL" "$ENV_FILE"
            env_set "CAIRN_OPENAI_MODEL" "$OPENAI_MODEL" "$ENV_FILE"
            env_comment "CAIRN_BEDROCK_MODEL" "$ENV_FILE"
            env_comment "CAIRN_GEMINI_API_KEY" "$ENV_FILE"
            ;;
        gemini)
            [ -n "$GEMINI_KEY" ] && env_set "CAIRN_GEMINI_API_KEY" "$GEMINI_KEY" "$ENV_FILE"
            env_set "CAIRN_GEMINI_MODEL" "$GEMINI_MODEL" "$ENV_FILE"
            env_comment "CAIRN_BEDROCK_MODEL" "$ENV_FILE"
            env_comment "CAIRN_OPENAI_API_KEY" "$ENV_FILE"
            ;;
    esac

    # Embeddings
    env_set "CAIRN_EMBEDDING_BACKEND" "$EMBEDDING_BACKEND" "$ENV_FILE"
    if [ "$EMBEDDING_BACKEND" = "local" ]; then
        env_set "CAIRN_EMBEDDING_MODEL" "all-MiniLM-L6-v2" "$ENV_FILE"
        env_set "CAIRN_EMBEDDING_DIMENSIONS" "384" "$ENV_FILE"
    else
        if [ -n "$EMBEDDING_MODEL" ]; then
            env_set "CAIRN_EMBEDDING_MODEL" "$EMBEDDING_MODEL" "$ENV_FILE"
        fi
        env_set "CAIRN_EMBEDDING_DIMENSIONS" "$EMBEDDING_DIMENSIONS" "$ENV_FILE"
    fi

    # Knowledge graph
    if [ "$GRAPH_ENABLED" = true ]; then
        env_set "CAIRN_GRAPH_BACKEND" "neo4j" "$ENV_FILE"
        env_set "CAIRN_KNOWLEDGE_EXTRACTION" "true" "$ENV_FILE"
    else
        env_comment "CAIRN_GRAPH_BACKEND" "$ENV_FILE"
        env_comment "CAIRN_KNOWLEDGE_EXTRACTION" "$ENV_FILE"
    fi

    # Custom tier extras
    if [ "$PROFILE_NUM" = "4" ]; then
        env_set "CAIRN_ENRICHMENT_ENABLED" "$ENRICHMENT_ENABLED" "$ENV_FILE"
        env_set "CAIRN_RERANKING" "$RERANKING_ENABLED" "$ENV_FILE"
        env_set "CAIRN_CORS_ORIGINS" "$CORS_ORIGINS" "$ENV_FILE"
    fi

    ok "Written to ${ENV_FILE}"
fi

# ──────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════"

TIER_LABEL="Custom"
case "$PROFILE_NUM" in
    1) TIER_LABEL="Local dev (enriched)" ;;
    2) TIER_LABEL="Recommended (knowledge)" ;;
    3) TIER_LABEL="Enterprise" ;;
esac

echo "  Tier:          ${TIER_LABEL}"
echo "  LLM:           ${LLM_BACKEND}"
echo "  Embeddings:    ${EMBEDDING_BACKEND}"
if [ "$GRAPH_ENABLED" = true ]; then
    echo "  Knowledge graph: enabled"
fi
if [ "$DRY_RUN" = true ]; then
    echo "  Config file:   ${ENV_FILE} (dry run — not written)"
else
    echo "  Config file:   ${ENV_FILE} (updated)"
fi
echo "═══════════════════════════════════════"
echo ""
