-- Migration 009: File content hashes for drift detection
-- Stores file hashes at memory creation time. Used by drift_check to identify
-- memories with stale file references.

ALTER TABLE memories ADD COLUMN IF NOT EXISTS file_hashes JSONB DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_memories_file_hashes
    ON memories USING gin (file_hashes jsonb_path_ops)
    WHERE file_hashes != '{}';
