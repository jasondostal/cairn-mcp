# Backup and Disaster Recovery

Cairn stores data in two databases: PostgreSQL (source of truth) and Neo4j
(knowledge graph, reconstructable). This guide covers automated backups,
restoration, and disaster recovery procedures.

## Quick Start

### Backup

```bash
./scripts/backup.sh --verbose
```

Creates a compressed archive in `./backups/` containing:
- `postgres.dump` — full PostgreSQL backup (custom format)
- `neo4j.json` — Neo4j graph export via APOC (optional)
- `backup.json` — metadata (version, timestamp, migration count)

### Restore

```bash
./scripts/restore.sh ./backups/cairn-backup-20260301-120000.tar.gz
```

Restores PostgreSQL and optionally Neo4j, then prompts you to restart cairn.

---

## What Gets Backed Up

| Component | Backed up | Source of truth | Notes |
|-----------|-----------|-----------------|-------|
| PostgreSQL | Yes (required) | Yes | Memories, work items, users, audit logs, settings, events, migrations |
| Neo4j | Yes (optional) | No | Knowledge graph, code graph. Reconstructable from PG via reconciliation + `code_index` |
| Docker volumes | Not directly | — | Volumes persist across restarts but are not backed up by these scripts |
| `.env` file | Not backed up | — | Back up separately — contains secrets (JWT key, DB passwords, API keys) |

**PostgreSQL is the critical path.** If you lose Neo4j data, cairn rebuilds
the knowledge graph from PostgreSQL on next boot via `reconcile_graph()`.
Code graph data requires re-running `code_index` on your repositories.

---

## Automated Backups with Cron

### Daily PostgreSQL backup (recommended minimum)

```bash
crontab -e
```

```cron
# Daily Cairn backup at 2am, keep 30 days
0 2 * * * /path/to/cairn/scripts/backup.sh --no-neo4j --retain-days 30

# Weekly full backup (PG + Neo4j) on Sunday at 3am, keep 90 days
0 3 * * 0 /path/to/cairn/scripts/backup.sh --retain-days 90
```

The backup script is silent by default (cron-friendly). Add `--verbose` to
see progress, or check the exit code:

| Exit code | Meaning |
|-----------|---------|
| 0 | Success |
| 1 | PostgreSQL backup failed |
| 2 | Neo4j export failed (non-fatal) |
| 3 | Configuration error (missing container, bad arguments) |

### Cron with logging

```cron
0 2 * * * /path/to/cairn/scripts/backup.sh --no-neo4j --verbose >> /var/log/cairn-backup.log 2>&1
```

---

## Remote Backup

Backups stored on the same host as the database aren't disaster recovery.
Copy them offsite.

### rsync to another host

```bash
# After backup, sync to remote
rsync -az ./backups/ remote-host:/backups/cairn/
```

### Combined in cron

```cron
0 2 * * * /path/to/cairn/scripts/backup.sh --no-neo4j && rsync -az /path/to/cairn/backups/ nas:/backups/cairn/
```

### S3 / object storage

```bash
aws s3 sync ./backups/ s3://my-bucket/cairn-backups/ --delete
```

---

## Restore Walkthrough

### 1. Stop cairn (optional but recommended)

```bash
docker compose stop cairn
```

This prevents writes during restore. The database container stays running.

### 2. Restore

```bash
./scripts/restore.sh ./backups/cairn-backup-20260301-120000.tar.gz
```

The script will:
1. Extract and validate the archive
2. Show backup metadata (version, timestamp, size)
3. Check migration compatibility
4. Ask for confirmation (type `restore` to proceed)
5. Restore PostgreSQL via `pg_restore`
6. Restore Neo4j if data is present (or skip with `--skip-neo4j`)

### 3. Restart cairn

```bash
docker compose restart cairn
```

On startup, cairn:
- Runs any pending migrations (safe if restoring an older backup)
- Reconciles the knowledge graph with PostgreSQL
- Verifies vector dimensions and indexes

### 4. Verify

```bash
curl -s http://localhost:8000/api/health
```

Check memory count, version, and health status.

---

## Script Options

### backup.sh

```
Usage: ./scripts/backup.sh [OPTIONS]

  --backup-dir DIR     Backup destination (default: ./backups)
  --retain-days N      Delete backups older than N days (default: 30, 0 = no rotation)
  --no-neo4j           Skip Neo4j graph export
  --verbose            Print progress to stdout (default: quiet for cron)
  --dry-run            Show what would happen without doing it
  --help               Show this help
```

### restore.sh

```
Usage: ./scripts/restore.sh BACKUP_FILE [OPTIONS]

  --skip-neo4j         Skip Neo4j restore (graph rebuilds from PG on next boot)
  --yes                Skip confirmation prompt
  --dry-run            Show what would happen without doing it
  --help               Show this help
```

---

## Docker Volume Snapshots

An alternative to `pg_dump` is snapshotting the Docker volumes directly.
This is faster for large databases but requires stopping the containers.

```bash
# Stop everything
docker compose down

# Snapshot volumes
docker run --rm -v cairn-pgdata:/data -v $(pwd)/backups:/backup \
  alpine tar -czf /backup/pgdata-snapshot.tar.gz -C /data .

docker run --rm -v cairn-neo4j:/data -v $(pwd)/backups:/backup \
  alpine tar -czf /backup/neo4j-snapshot.tar.gz -C /data .

# Restart
docker compose up -d
```

To restore a volume snapshot:

```bash
docker compose down
docker volume rm cairn-pgdata  # destroys current data

docker run --rm -v cairn-pgdata:/data -v $(pwd)/backups:/backup \
  alpine tar -xzf /backup/pgdata-snapshot.tar.gz -C /data

docker compose up -d
```

**Trade-offs:** Volume snapshots are faster and capture everything (including
WAL state), but require downtime and are not portable across PostgreSQL
versions. `pg_dump` is slower but works across versions and allows selective
restore.

---

## Disaster Recovery Scenarios

### Host failure (total loss)

1. Provision a new host
2. Install Docker, clone the cairn repo
3. Copy `.env` file (you backed this up separately, right?)
4. `docker compose up -d` — starts fresh containers
5. `./scripts/restore.sh /path/to/latest-backup.tar.gz --yes`
6. `docker compose restart cairn`

### Data corruption

1. Identify the last known-good backup
2. `docker compose stop cairn`
3. `./scripts/restore.sh /path/to/backup.tar.gz`
4. `docker compose restart cairn`
5. Check audit logs for what happened between backup and corruption

### Accidental deletion (single table/row)

For surgical recovery, use `pg_restore` with table selection:

```bash
# Extract the backup
tar -xzf cairn-backup-20260301-120000.tar.gz
cd cairn-backup-20260301-120000

# List tables in the dump
docker exec -i cairn-db pg_restore --list postgres.dump | grep TABLE

# Restore a single table (appends, does not replace)
docker exec -i cairn-db pg_restore -U cairn -d cairn \
  --data-only --table=memories postgres.dump
```

### Migration rollback

If a migration breaks things:

1. Restore from the most recent pre-migration backup
2. Pin the cairn image to the previous version in `docker-compose.yml`
3. `docker compose up -d cairn`
4. Report the issue

---

## Credential Security

The backup scripts read database credentials from environment variables
or the `.env` file. The credentials are **not stored in the backup archive**.

Back up your `.env` file separately and securely — it contains:
- `CAIRN_DB_PASS` — PostgreSQL password
- `CAIRN_AUTH_JWT_SECRET` — JWT signing key
- `CAIRN_OIDC_CLIENT_SECRET` — OIDC provider secret (if using SSO)
- AWS credentials (if using Bedrock)

```bash
# Example: encrypted .env backup
gpg --symmetric --cipher-algo AES256 .env
# Produces .env.gpg — store this alongside your database backups
```
