-- Migration 048: Add tool_name column to usage_events (ca-231).
--
-- Closes observability gap #4: usage_events had no tool attribution.
-- MCP tool handlers now set tool_name on the trace context, and
-- track_operation() writes it through to this column.

ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS tool_name VARCHAR(100);

-- Index for per-tool analytics queries
CREATE INDEX IF NOT EXISTS idx_usage_events_tool_name
    ON usage_events (tool_name)
    WHERE tool_name IS NOT NULL;
