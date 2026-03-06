-- Migration 047: Unified Memory — absorb working_memory into memories.
--
-- Working memory items are just memories with salience decay. This migration
-- adds salience + pinned columns to memories and migrates all working_memory
-- rows into the memories table. The working_memory table is preserved but
-- renamed for rollback safety.
--
-- Design doc: cairn project doc #110 (ca-173)

-- Step 1: Add lifecycle columns to memories
ALTER TABLE memories ADD COLUMN IF NOT EXISTS salience REAL;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;

-- Step 2: Index for ephemeral item queries (salience IS NOT NULL = ephemeral)
CREATE INDEX IF NOT EXISTS idx_memories_salience
    ON memories (salience DESC NULLS LAST)
    WHERE salience IS NOT NULL AND is_active = true;

-- Step 3: Migrate working_memory rows into memories
INSERT INTO memories (
    content, memory_type, importance, project_id, session_name,
    embedding, salience, pinned, author, is_active, inactive_reason,
    created_at, updated_at
)
SELECT
    wm.content,
    wm.item_type,                                          -- becomes memory_type
    0.5,                                                   -- default importance
    wm.project_id,
    wm.session_name,
    wm.embedding,
    CASE WHEN wm.status = 'active' THEN wm.salience ELSE NULL END,
    wm.pinned,
    wm.author,
    wm.status != 'archived',                               -- archived -> is_active=false
    CASE WHEN wm.status = 'archived' THEN 'migrated from working_memory (archived)'
         WHEN wm.status = 'resolved' THEN 'migrated from working_memory (resolved: ' || COALESCE(wm.resolved_into, 'unknown') || ')'
         ELSE NULL END,
    wm.created_at,
    wm.updated_at
FROM working_memory wm;

-- Step 4: Rename old table (preserved for rollback, drop in a future migration)
ALTER TABLE IF EXISTS working_memory RENAME TO working_memory_deprecated;
