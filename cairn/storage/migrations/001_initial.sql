-- Cairn: Initial schema
-- Migration 001: Core tables, indexes, pgvector extension

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Projects: organizational container
CREATE TABLE IF NOT EXISTS projects (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Memories: the core unit of knowledge
CREATE TABLE IF NOT EXISTS memories (
    id              SERIAL PRIMARY KEY,
    content         TEXT NOT NULL,
    summary         TEXT,
    memory_type     VARCHAR(50) NOT NULL DEFAULT 'note',
    importance      FLOAT NOT NULL DEFAULT 0.5,

    -- Organization
    project_id      INTEGER REFERENCES projects(id),
    session_name    VARCHAR(255),

    -- Embedding (384-dim, MiniLM-L6-v2)
    embedding       vector(384),

    -- Enrichment
    tags            TEXT[] DEFAULT '{}',
    auto_tags       TEXT[] DEFAULT '{}',

    -- Related files
    related_files   TEXT[] DEFAULT '{}',

    -- Lifecycle
    is_active       BOOLEAN DEFAULT true,
    inactive_reason TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Project documents (briefs, PRDs, plans)
CREATE TABLE IF NOT EXISTS project_documents (
    id          SERIAL PRIMARY KEY,
    project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    doc_type    VARCHAR(50) NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Project links
CREATE TABLE IF NOT EXISTS project_links (
    id          SERIAL PRIMARY KEY,
    source_id   INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    target_id   INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    link_type   VARCHAR(50) DEFAULT 'related',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_id, target_id)
);

-- Memory relationships
CREATE TABLE IF NOT EXISTS memory_relations (
    source_id   INTEGER REFERENCES memories(id) ON DELETE CASCADE,
    target_id   INTEGER REFERENCES memories(id) ON DELETE CASCADE,
    relation    VARCHAR(50) DEFAULT 'related',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (source_id, target_id)
);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER REFERENCES projects(id),
    description     TEXT NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS task_memory_links (
    task_id     INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    memory_id   INTEGER REFERENCES memories(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, memory_id)
);

-- ============================================================
-- INDEXES
-- ============================================================

-- Vector similarity search (HNSW)
CREATE INDEX IF NOT EXISTS idx_memories_embedding
    ON memories USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search (keyword leg of hybrid search)
CREATE INDEX IF NOT EXISTS idx_memories_fts
    ON memories USING gin (to_tsvector('english', content));

-- Tag search
CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories USING gin (tags);
CREATE INDEX IF NOT EXISTS idx_memories_auto_tags ON memories USING gin (auto_tags);

-- Common query patterns
CREATE INDEX IF NOT EXISTS idx_memories_project_active ON memories (project_id, is_active);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories (memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories (importance DESC);

-- Insert the global project
INSERT INTO projects (name) VALUES ('__global__') ON CONFLICT (name) DO NOTHING;
