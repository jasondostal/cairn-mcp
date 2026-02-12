-- Migration 011: Dashboard performance indexes
-- Supports memory-growth, sparkline, and heatmap queries

CREATE INDEX IF NOT EXISTS idx_memories_created_type
    ON memories (created_at, memory_type)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_cairns_set_at
    ON cairns (set_at DESC)
    WHERE set_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_usage_events_model_ts
    ON usage_events (model, timestamp DESC)
    WHERE model IS NOT NULL;
