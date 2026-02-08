-- Cairn: Partial indexes for active memories
-- Migration 005: Optimize the most common query pattern (is_active = true)

-- Partial index for timeline queries: active memories by project, ordered by created_at
CREATE INDEX IF NOT EXISTS idx_memories_active_project_created
    ON memories (project_id, created_at DESC)
    WHERE is_active = true;

-- Partial index for session grouping: active memories by session
CREATE INDEX IF NOT EXISTS idx_memories_active_session
    ON memories (project_id, session_name)
    WHERE is_active = true AND session_name IS NOT NULL;
