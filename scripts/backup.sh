#!/usr/bin/env bash
# Cairn Backup Script
# Creates compressed backups of PostgreSQL (required) and Neo4j (optional).
# Designed for cron — silent on success unless --verbose, non-zero exit on failure.
#
# Usage: ./scripts/backup.sh [OPTIONS]
#
# Options:
#   --backup-dir DIR     Backup destination (default: ./backups)
#   --retain-days N      Delete backups older than N days (default: 30, 0 = no rotation)
#   --no-neo4j           Skip Neo4j graph export
#   --verbose            Print progress to stdout (default: quiet for cron)
#   --dry-run            Show what would happen without doing it
#   --help               Show this help

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

VERBOSE=false
DRY_RUN=false

log()  { $VERBOSE && echo -e "${BLUE}[backup]${NC} $*" || true; }
ok()   { $VERBOSE && echo -e "${GREEN}  [ok]${NC} $*" || true; }
warn() { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
fail() { echo -e "${RED}[fail]${NC} $*" >&2; }

# ──────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

BACKUP_DIR="${PROJECT_DIR}/backups"
RETAIN_DAYS=30
INCLUDE_NEO4J=true

# Container names (match docker-compose.yml)
PG_CONTAINER="cairn-db"
NEO4J_CONTAINER="cairn-graph"
CAIRN_CONTAINER="cairn"

# ──────────────────────────────────────────────
# Parse arguments
# ──────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backup-dir)  BACKUP_DIR="$2"; shift 2 ;;
        --retain-days) RETAIN_DAYS="$2"; shift 2 ;;
        --no-neo4j)    INCLUDE_NEO4J=false; shift ;;
        --verbose)     VERBOSE=true; shift ;;
        --dry-run)     DRY_RUN=true; VERBOSE=true; shift ;;
        --help|-h)
            head -14 "$0" | tail -12 | sed 's/^# \?//'
            exit 0
            ;;
        *)
            fail "Unknown option: $1"
            exit 3
            ;;
    esac
done

# ──────────────────────────────────────────────
# Resolve database credentials
# ──────────────────────────────────────────────

resolve_config() {
    # Priority: env vars > .env file > docker-compose defaults
    if [[ -z "${CAIRN_DB_USER:-}" ]] && [[ -f "${PROJECT_DIR}/.env" ]]; then
        log "Loading credentials from .env"
        # Safe .env loading — handles unquoted values with spaces
        while IFS='=' read -r key value; do
            # Skip comments and blank lines
            [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
            key=$(echo "$key" | xargs)
            # Only import CAIRN_ vars we need
            case "$key" in
                CAIRN_DB_USER|CAIRN_DB_NAME|CAIRN_DB_PASS|CAIRN_NEO4J_USER|CAIRN_NEO4J_PASSWORD)
                    export "$key=$value"
                    ;;
            esac
        done < "${PROJECT_DIR}/.env"
    fi

    DB_USER="${CAIRN_DB_USER:-cairn}"
    DB_NAME="${CAIRN_DB_NAME:-cairn}"
    DB_PASS="${CAIRN_DB_PASS:-cairn-dev-password}"
    NEO4J_USER="${CAIRN_NEO4J_USER:-neo4j}"
    NEO4J_PASS="${CAIRN_NEO4J_PASSWORD:-cairn-dev-password}"
}

# ──────────────────────────────────────────────
# Pre-flight checks
# ──────────────────────────────────────────────

preflight() {
    local errors=0

    if ! command -v docker &>/dev/null; then
        fail "docker not found in PATH"
        exit 3
    fi

    if ! docker ps --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
        fail "Container '${PG_CONTAINER}' is not running"
        ((errors++))
    fi

    if $INCLUDE_NEO4J && ! docker ps --format '{{.Names}}' | grep -q "^${NEO4J_CONTAINER}$"; then
        warn "Container '${NEO4J_CONTAINER}' is not running — skipping Neo4j export"
        INCLUDE_NEO4J=false
    fi

    if [[ $errors -gt 0 ]]; then
        fail "Pre-flight failed. Is docker compose running?"
        exit 3
    fi
}

# ──────────────────────────────────────────────
# Backup PostgreSQL
# ──────────────────────────────────────────────

backup_postgres() {
    local dest="$1"
    log "Dumping PostgreSQL (${DB_NAME})..."

    if $DRY_RUN; then
        log "[dry-run] docker exec ${PG_CONTAINER} pg_dump -U ${DB_USER} -d ${DB_NAME} -Fc > ${dest}/postgres.dump"
        return 0
    fi

    if docker exec "${PG_CONTAINER}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" -Fc > "${dest}/postgres.dump" 2>/dev/null; then
        local size
        size=$(du -h "${dest}/postgres.dump" | cut -f1)
        ok "PostgreSQL dump: ${size}"
    else
        fail "PostgreSQL dump failed"
        return 1
    fi
}

# ──────────────────────────────────────────────
# Backup Neo4j via APOC JSON export
# ──────────────────────────────────────────────

backup_neo4j() {
    local dest="$1"
    log "Exporting Neo4j graph..."

    if $DRY_RUN; then
        log "[dry-run] docker exec ${NEO4J_CONTAINER} cypher-shell ... > ${dest}/neo4j.json"
        return 0
    fi

    # Use APOC JSON streaming export — works on running Community Edition
    if docker exec "${NEO4J_CONTAINER}" cypher-shell \
        -u "${NEO4J_USER}" -p "${NEO4J_PASS}" \
        --format plain \
        "CALL apoc.export.json.all(null, {stream:true}) YIELD data RETURN data;" \
        2>/dev/null | grep -v '^data$' | grep -v '^$' > "${dest}/neo4j.json"; then

        local size
        size=$(du -h "${dest}/neo4j.json" | cut -f1)
        # Check if export is empty (no nodes)
        if [[ ! -s "${dest}/neo4j.json" ]]; then
            warn "Neo4j export is empty (no graph data)"
            rm -f "${dest}/neo4j.json"
        else
            ok "Neo4j export: ${size}"
        fi
    else
        warn "Neo4j export failed (non-fatal — graph is reconstructable from PG)"
        rm -f "${dest}/neo4j.json"
        return 2
    fi
}

# ──────────────────────────────────────────────
# Write backup metadata
# ──────────────────────────────────────────────

write_metadata() {
    local dest="$1"
    log "Writing backup metadata..."

    if $DRY_RUN; then
        log "[dry-run] Would write ${dest}/backup.json"
        return 0
    fi

    # Get Cairn version
    local version="unknown"
    if docker ps --format '{{.Names}}' | grep -q "^${CAIRN_CONTAINER}$"; then
        version=$(docker exec "${CAIRN_CONTAINER}" grep '^version' pyproject.toml 2>/dev/null | head -1 | sed 's/.*"\(.*\)"/\1/' || echo "unknown")
    fi

    # Get migration count from PG
    local migration_count=0
    migration_count=$(docker exec "${PG_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -tAc \
        "SELECT COUNT(*) FROM _migrations;" 2>/dev/null || echo "0")

    # Get PG database size
    local pg_size="unknown"
    pg_size=$(docker exec "${PG_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -tAc \
        "SELECT pg_size_pretty(pg_database_size('${DB_NAME}'));" 2>/dev/null || echo "unknown")

    # Get Neo4j counts
    local neo4j_nodes=0 neo4j_rels=0
    if $INCLUDE_NEO4J; then
        neo4j_nodes=$(docker exec "${NEO4J_CONTAINER}" cypher-shell \
            -u "${NEO4J_USER}" -p "${NEO4J_PASS}" --format plain \
            "MATCH (n) RETURN count(n);" 2>/dev/null | tail -1 || echo "0")
        neo4j_rels=$(docker exec "${NEO4J_CONTAINER}" cypher-shell \
            -u "${NEO4J_USER}" -p "${NEO4J_PASS}" --format plain \
            "MATCH ()-[r]->() RETURN count(r);" 2>/dev/null | tail -1 || echo "0")
    fi

    cat > "${dest}/backup.json" <<METAEOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "hostname": "$(hostname)",
  "cairn_version": "${version}",
  "migration_count": ${migration_count},
  "pg_size": "${pg_size}",
  "neo4j_nodes": ${neo4j_nodes},
  "neo4j_relationships": ${neo4j_rels},
  "includes_neo4j": $([ -f "${dest}/neo4j.json" ] && echo "true" || echo "false")
}
METAEOF

    ok "Metadata written (v${version}, ${migration_count} migrations, PG ${pg_size})"
}

# ──────────────────────────────────────────────
# Compress and clean up
# ──────────────────────────────────────────────

compress() {
    local dest="$1"
    local archive_name
    archive_name="$(basename "${dest}").tar.gz"
    local archive_path="${BACKUP_DIR}/${archive_name}"

    log "Compressing..."

    if $DRY_RUN; then
        log "[dry-run] tar -czf ${archive_path} -C ${BACKUP_DIR} $(basename "${dest}")"
        return 0
    fi

    tar -czf "${archive_path}" -C "${BACKUP_DIR}" "$(basename "${dest}")"
    rm -rf "${dest}"

    local size
    size=$(du -h "${archive_path}" | cut -f1)
    ok "Archive: ${archive_path} (${size})"
}

# ──────────────────────────────────────────────
# Rotate old backups
# ──────────────────────────────────────────────

rotate() {
    if [[ "${RETAIN_DAYS}" -eq 0 ]]; then
        log "Rotation disabled (--retain-days 0)"
        return 0
    fi

    log "Rotating backups older than ${RETAIN_DAYS} days..."

    if [[ ! -d "${BACKUP_DIR}" ]]; then
        return 0
    fi

    if $DRY_RUN; then
        local old_count
        old_count=$(find "${BACKUP_DIR}" -maxdepth 1 -name "cairn-backup-*.tar.gz" -mtime "+${RETAIN_DAYS}" 2>/dev/null | wc -l)
        log "[dry-run] Would delete ${old_count} old backup(s)"
        return 0
    fi

    local deleted=0
    while IFS= read -r old_backup; do
        rm -f "${old_backup}"
        ((deleted++))
    done < <(find "${BACKUP_DIR}" -maxdepth 1 -name "cairn-backup-*.tar.gz" -mtime "+${RETAIN_DAYS}" 2>/dev/null)

    if [[ $deleted -gt 0 ]]; then
        ok "Rotated ${deleted} old backup(s)"
    fi
}

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

main() {
    local timestamp
    timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_name="cairn-backup-${timestamp}"
    local dest="${BACKUP_DIR}/${backup_name}"

    resolve_config
    preflight

    log "Starting backup → ${dest}"

    if ! $DRY_RUN; then
        mkdir -p "${dest}"
    fi

    # PostgreSQL (required)
    if ! backup_postgres "${dest}"; then
        rm -rf "${dest}"
        exit 1
    fi

    # Neo4j (optional)
    local neo4j_exit=0
    if $INCLUDE_NEO4J; then
        backup_neo4j "${dest}" || neo4j_exit=$?
    fi

    # Metadata
    write_metadata "${dest}"

    # Compress
    compress "${dest}"

    # Rotate
    rotate

    # Summary
    if $VERBOSE; then
        echo ""
        echo -e "${BOLD}Backup complete${NC}"
        echo "  Archive:   ${BACKUP_DIR}/${backup_name}.tar.gz"
        echo "  Retention: ${RETAIN_DAYS} days"
        if [[ $neo4j_exit -ne 0 ]]; then
            echo -e "  Neo4j:     ${YELLOW}skipped (export failed, graph is reconstructable)${NC}"
        fi
    fi

    exit 0
}

main
