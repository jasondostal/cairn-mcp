-- Memory lifecycle: access tracking columns for decay and controlled forgetting.
-- Non-destructive: adds columns with defaults, existing rows get access_count=0
-- and last_accessed_at=NULL (never accessed).

ALTER TABLE memories ADD COLUMN IF NOT EXISTS access_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ;

-- Index for decay scoring: find memories by last access time.
-- Partial index on active memories only (inactive ones are already "forgotten").
CREATE INDEX IF NOT EXISTS idx_memories_last_accessed
    ON memories (last_accessed_at)
    WHERE is_active = true;

-- Composite index for the controlled forgetting scanner:
-- find active memories sorted by access recency.
CREATE INDEX IF NOT EXISTS idx_memories_decay_candidates
    ON memories (last_accessed_at NULLS FIRST, access_count)
    WHERE is_active = true;
