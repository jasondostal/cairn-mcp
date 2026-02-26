-- Migration 033: Trace context columns for end-to-end operation correlation.
-- Phase 1 of Watchtower (v0.63.0): every operation gets trace_id + span_id.

-- usage_events: per-operation trace context
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS trace_id VARCHAR(32);
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS span_id VARCHAR(16);
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS parent_span_id VARCHAR(16);

-- events: trace_id for event bus correlation
ALTER TABLE events ADD COLUMN IF NOT EXISTS trace_id VARCHAR(32);

-- Partial indexes: zero overhead on old rows, efficient for trace queries
CREATE INDEX IF NOT EXISTS idx_usage_events_trace_id
    ON usage_events (trace_id) WHERE trace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_trace_id
    ON events (trace_id) WHERE trace_id IS NOT NULL;
