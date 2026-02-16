-- v0.47.0: Graph-native hierarchical work items
-- Replaces flat tasks for structured work management

CREATE TABLE IF NOT EXISTS work_items (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    short_id VARCHAR(64) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    acceptance_criteria TEXT,
    item_type VARCHAR(20) NOT NULL DEFAULT 'task',
    priority INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    parent_id INTEGER REFERENCES work_items(id) ON DELETE SET NULL,
    assignee VARCHAR(255),
    claimed_at TIMESTAMPTZ,
    session_name VARCHAR(255),
    embedding vector(384),
    metadata JSONB DEFAULT '{}',
    graph_uuid UUID,
    graph_synced BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ
);

-- Junction: work items <-> memories
CREATE TABLE IF NOT EXISTS work_item_memory_links (
    work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    memory_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (work_item_id, memory_id)
);

-- Dependency edges: blocker blocks blocked
CREATE TABLE IF NOT EXISTS work_item_blocks (
    blocker_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    blocked_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (blocker_id, blocked_id),
    CHECK (blocker_id != blocked_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_work_items_project_status ON work_items (project_id, status);
CREATE INDEX IF NOT EXISTS idx_work_items_parent ON work_items (parent_id);
CREATE INDEX IF NOT EXISTS idx_work_items_assignee ON work_items (assignee);
CREATE INDEX IF NOT EXISTS idx_work_items_priority ON work_items (priority DESC);
CREATE INDEX IF NOT EXISTS idx_work_items_short_id ON work_items (short_id);
CREATE INDEX IF NOT EXISTS idx_work_items_created ON work_items (created_at DESC);

-- Graph repair: find unsynced items
CREATE INDEX IF NOT EXISTS idx_work_items_graph_repair
    ON work_items (id) WHERE graph_synced = false AND graph_uuid IS NULL;

-- HNSW vector index on embedding
CREATE INDEX IF NOT EXISTS idx_work_items_embedding
    ON work_items USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Fulltext search on title + description
CREATE INDEX IF NOT EXISTS idx_work_items_fulltext
    ON work_items USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')));
