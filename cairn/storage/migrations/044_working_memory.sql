-- Migration 044: Persistent working memory — active cognitive workspace
--
-- Stores pre-crystallized cognitive items (hypotheses, questions, tensions,
-- connections, threads, intuitions) that persist across sessions. Items have
-- salience scores that decay over time and can be boosted through engagement.
--
-- Shared scratch pad for active thoughts that persist across sessions.

CREATE TABLE IF NOT EXISTS working_memory (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    item_type       VARCHAR(50) NOT NULL DEFAULT 'thread',
    salience        REAL NOT NULL DEFAULT 0.7,
    author          VARCHAR(255),
    pinned          BOOLEAN NOT NULL DEFAULT FALSE,
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
    resolved_into   VARCHAR(50),        -- memory, belief, work_item, decision, thinking_sequence
    resolution_id   VARCHAR(100),       -- ID of the resolved-into entity
    resolution_note TEXT,
    embedding       vector(384),
    session_name    VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at     TIMESTAMPTZ
);

-- Primary query: active items for a project, sorted by salience
CREATE INDEX IF NOT EXISTS idx_working_memory_project_active
    ON working_memory (project_id, status, salience DESC)
    WHERE status = 'active';

-- Author filter
CREATE INDEX IF NOT EXISTS idx_working_memory_author
    ON working_memory (author, status);

-- Type filter
CREATE INDEX IF NOT EXISTS idx_working_memory_type
    ON working_memory (item_type, status);

-- Embedding similarity search (HNSW)
CREATE INDEX IF NOT EXISTS idx_working_memory_embedding
    ON working_memory USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
