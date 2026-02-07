-- Cairn: Clustering schema
-- Migration 002: Cluster tables for Phase 3 pattern discovery

-- Clusters: groups of semantically similar memories
CREATE TABLE IF NOT EXISTS clusters (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    label           VARCHAR(255) NOT NULL DEFAULT 'Unlabeled Cluster',
    summary         TEXT,
    centroid        vector(384),
    member_count    INTEGER NOT NULL DEFAULT 0,
    avg_distance    FLOAT,
    confidence      FLOAT NOT NULL DEFAULT 0.0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Cluster members: which memories belong to which clusters
CREATE TABLE IF NOT EXISTS cluster_members (
    cluster_id      INTEGER REFERENCES clusters(id) ON DELETE CASCADE,
    memory_id       INTEGER REFERENCES memories(id) ON DELETE CASCADE,
    distance        FLOAT NOT NULL DEFAULT 0.0,
    PRIMARY KEY (cluster_id, memory_id)
);

-- Clustering runs: audit trail + staleness detection
CREATE TABLE IF NOT EXISTS clustering_runs (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    memory_count    INTEGER NOT NULL DEFAULT 0,
    cluster_count   INTEGER NOT NULL DEFAULT 0,
    noise_count     INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_clusters_project ON clusters (project_id);
CREATE INDEX IF NOT EXISTS idx_cluster_members_memory ON cluster_members (memory_id);
CREATE INDEX IF NOT EXISTS idx_clustering_runs_project_created ON clustering_runs (project_id, created_at DESC);
