#!/usr/bin/env bash
# Cairn Restore Script
# Restores PostgreSQL and optionally Neo4j from a backup archive.
#
# Usage: ./scripts/restore.sh BACKUP_FILE [OPTIONS]
#
# Options:
#   --skip-neo4j         Skip Neo4j restore (graph rebuilds from PG on next boot)
#   --yes                Skip confirmation prompt
#   --dry-run            Show what would happen without doing it
#   --help               Show this help
#
# After restore, restart the cairn container to run migrations and reconciliation.

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

DRY_RUN=false

log()  { echo -e "${BLUE}[restore]${NC} $*"; }
ok()   { echo -e "${GREEN}     [ok]${NC} $*"; }
warn() { echo -e "${YELLOW}   [warn]${NC} $*"; }
fail() { echo -e "${RED}   [fail]${NC} $*" >&2; }

# ──────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

BACKUP_FILE=""
SKIP_NEO4J=false
AUTO_YES=false

# Container names
PG_CONTAINER="cairn-db"
NEO4J_CONTAINER="cairn-graph"

# ──────────────────────────────────────────────
# Parse arguments
# ──────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-neo4j) SKIP_NEO4J=true; shift ;;
        --yes|-y)     AUTO_YES=true; shift ;;
        --dry-run)    DRY_RUN=true; shift ;;
        --help|-h)
            head -14 "$0" | tail -12 | sed 's/^# \?//'
            exit 0
            ;;
        -*)
            fail "Unknown option: $1"
            exit 3
            ;;
        *)
            BACKUP_FILE="$1"; shift
            ;;
    esac
done

if [[ -z "${BACKUP_FILE}" ]]; then
    fail "Usage: restore.sh BACKUP_FILE [OPTIONS]"
    fail "Run with --help for details."
    exit 3
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
    fail "Backup file not found: ${BACKUP_FILE}"
    exit 3
fi

# ──────────────────────────────────────────────
# Resolve database credentials
# ──────────────────────────────────────────────

resolve_config() {
    if [[ -z "${CAIRN_DB_USER:-}" ]] && [[ -f "${PROJECT_DIR}/.env" ]]; then
        log "Loading credentials from .env"
        # Safe .env loading — handles unquoted values with spaces
        while IFS='=' read -r key value; do
            [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
            key=$(echo "$key" | xargs)
            case "$key" in
                CAIRN_DB_USER|CAIRN_DB_NAME|CAIRN_DB_PASS|CAIRN_NEO4J_USER|CAIRN_NEO4J_PASSWORD)
                    export "$key=$value"
                    ;;
            esac
        done < "${PROJECT_DIR}/.env"
    fi

    DB_USER="${CAIRN_DB_USER:-cairn}"
    DB_NAME="${CAIRN_DB_NAME:-cairn}"
    NEO4J_USER="${CAIRN_NEO4J_USER:-neo4j}"
    NEO4J_PASS="${CAIRN_NEO4J_PASSWORD:-cairn-dev-password}"
}

# ──────────────────────────────────────────────
# Extract and inspect backup
# ──────────────────────────────────────────────

extract_backup() {
    TEMP_DIR=$(mktemp -d)
    trap 'rm -rf "${TEMP_DIR}"' EXIT

    log "Extracting ${BACKUP_FILE}..."
    tar -xzf "${BACKUP_FILE}" -C "${TEMP_DIR}"

    # Find the backup directory inside the archive
    BACKUP_DIR=$(find "${TEMP_DIR}" -name "backup.json" -printf '%h\n' 2>/dev/null | head -1)

    if [[ -z "${BACKUP_DIR}" ]] || [[ ! -f "${BACKUP_DIR}/backup.json" ]]; then
        fail "Invalid backup archive — no backup.json found"
        exit 3
    fi

    if [[ ! -f "${BACKUP_DIR}/postgres.dump" ]]; then
        fail "Invalid backup archive — no postgres.dump found"
        exit 3
    fi
}

inspect_backup() {
    log "Backup contents:"

    # Parse metadata (portable — no jq dependency)
    local version timestamp pg_size migrations includes_neo4j
    version=$(grep '"cairn_version"' "${BACKUP_DIR}/backup.json" | sed 's/.*: *"\([^"]*\)".*/\1/')
    timestamp=$(grep '"timestamp"' "${BACKUP_DIR}/backup.json" | sed 's/.*: *"\([^"]*\)".*/\1/')
    pg_size=$(grep '"pg_size"' "${BACKUP_DIR}/backup.json" | sed 's/.*: *"\([^"]*\)".*/\1/')
    migrations=$(grep '"migration_count"' "${BACKUP_DIR}/backup.json" | sed 's/.*: *\([0-9]*\).*/\1/')
    includes_neo4j=$(grep '"includes_neo4j"' "${BACKUP_DIR}/backup.json" | sed 's/.*: *\(true\|false\).*/\1/')

    echo "  Cairn version:  ${version}"
    echo "  Timestamp:      ${timestamp}"
    echo "  PG size:        ${pg_size}"
    echo "  Migrations:     ${migrations}"
    echo "  Includes Neo4j: ${includes_neo4j}"

    # Store for safety check
    BACKUP_MIGRATIONS="${migrations}"
    BACKUP_HAS_NEO4J="${includes_neo4j}"
}

# ──────────────────────────────────────────────
# Safety checks
# ──────────────────────────────────────────────

safety_check() {
    if ! docker ps --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
        fail "Container '${PG_CONTAINER}' is not running"
        exit 3
    fi

    # Compare migration counts
    local current_migrations
    current_migrations=$(docker exec "${PG_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -tAc \
        "SELECT COUNT(*) FROM _migrations;" 2>/dev/null || echo "0")

    if [[ "${current_migrations}" -gt "${BACKUP_MIGRATIONS}" ]]; then
        warn "Current DB has ${current_migrations} migrations but backup has ${BACKUP_MIGRATIONS}"
        warn "Restoring an older backup into a newer schema may cause issues"
        warn "After restore, restart cairn to re-run pending migrations"
    fi
}

# ──────────────────────────────────────────────
# Confirmation
# ──────────────────────────────────────────────

confirm() {
    if $AUTO_YES || $DRY_RUN; then
        return 0
    fi

    echo ""
    echo -e "${BOLD}${RED}WARNING: This will REPLACE all data in ${PG_CONTAINER}.${NC}"
    if ! $SKIP_NEO4J && [[ "${BACKUP_HAS_NEO4J}" == "true" ]]; then
        echo -e "${BOLD}${RED}Neo4j graph data will also be replaced.${NC}"
    fi
    echo ""
    read -rp "Type 'restore' to confirm: " answer
    if [[ "${answer}" != "restore" ]]; then
        log "Aborted."
        exit 0
    fi
}

# ──────────────────────────────────────────────
# Restore PostgreSQL
# ──────────────────────────────────────────────

restore_postgres() {
    log "Restoring PostgreSQL..."

    if $DRY_RUN; then
        log "[dry-run] docker exec -i ${PG_CONTAINER} pg_restore -U ${DB_USER} -d ${DB_NAME} --clean --if-exists < postgres.dump"
        return 0
    fi

    # Drop and recreate to ensure clean state
    # pg_restore --clean handles this, but we also need to handle the case
    # where the backup has tables that don't exist in the current schema
    if docker exec -i "${PG_CONTAINER}" pg_restore \
        -U "${DB_USER}" \
        -d "${DB_NAME}" \
        --clean \
        --if-exists \
        --no-owner \
        --no-privileges \
        --single-transaction \
        < "${BACKUP_DIR}/postgres.dump" 2>/dev/null; then
        ok "PostgreSQL restored"
    else
        # pg_restore returns non-zero for warnings (e.g., "table does not exist" on --clean)
        # Check if the database is actually usable
        local table_count
        table_count=$(docker exec "${PG_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -tAc \
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")
        if [[ "${table_count}" -gt 0 ]]; then
            ok "PostgreSQL restored (with warnings — this is normal for --clean)"
        else
            fail "PostgreSQL restore failed — no tables found after restore"
            return 1
        fi
    fi
}

# ──────────────────────────────────────────────
# Restore Neo4j
# ──────────────────────────────────────────────

restore_neo4j() {
    if $SKIP_NEO4J; then
        log "Skipping Neo4j restore (--skip-neo4j)"
        log "Graph will rebuild from PG on next cairn restart via reconciliation"
        return 0
    fi

    if [[ "${BACKUP_HAS_NEO4J}" != "true" ]] || [[ ! -f "${BACKUP_DIR}/neo4j.json" ]]; then
        log "No Neo4j data in backup — graph will rebuild from PG on next cairn restart"
        return 0
    fi

    if ! docker ps --format '{{.Names}}' | grep -q "^${NEO4J_CONTAINER}$"; then
        warn "Container '${NEO4J_CONTAINER}' is not running — skipping Neo4j restore"
        return 0
    fi

    log "Restoring Neo4j graph..."

    if $DRY_RUN; then
        log "[dry-run] Would clear Neo4j graph and import from neo4j.json"
        return 0
    fi

    # Clear existing graph in batches to avoid OOM
    log "Clearing existing graph data..."
    local deleted=1
    while [[ $deleted -gt 0 ]]; do
        deleted=$(docker exec "${NEO4J_CONTAINER}" cypher-shell \
            -u "${NEO4J_USER}" -p "${NEO4J_PASS}" --format plain \
            "MATCH (n) WITH n LIMIT 10000 DETACH DELETE n RETURN count(*);" \
            2>/dev/null | tail -1 || echo "0")
        deleted=$(echo "${deleted}" | tr -d '[:space:]')
        [[ -z "${deleted}" ]] && deleted=0
    done

    # Copy export file into container and import
    docker cp "${BACKUP_DIR}/neo4j.json" "${NEO4J_CONTAINER}:/tmp/neo4j-restore.json"

    if docker exec "${NEO4J_CONTAINER}" cypher-shell \
        -u "${NEO4J_USER}" -p "${NEO4J_PASS}" \
        "CALL apoc.import.json('file:///tmp/neo4j-restore.json');" 2>/dev/null; then
        ok "Neo4j graph restored"
    else
        warn "Neo4j import failed (non-fatal — graph will rebuild from PG on next cairn restart)"
    fi

    # Clean up temp file
    docker exec "${NEO4J_CONTAINER}" rm -f /tmp/neo4j-restore.json 2>/dev/null || true
}

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

main() {
    resolve_config
    extract_backup
    inspect_backup
    safety_check
    confirm

    restore_postgres || exit 1
    restore_neo4j

    echo ""
    echo -e "${BOLD}Restore complete.${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Restart cairn to re-run migrations and graph reconciliation:"
    echo "     docker compose restart cairn"
    echo "  2. Verify health:"
    echo "     curl -s http://localhost:8000/api/health"
    echo ""
}

main
