-- Cairn v0.41.0: Agent metadata + session lifecycle
-- Adds multi-agent support (agent_id, agent_type, parent_session)
-- Adds explicit session close tracking (closed_at, synthesis)

-- Agent identity columns
ALTER TABLE session_events ADD COLUMN IF NOT EXISTS agent_id VARCHAR(255);
ALTER TABLE session_events ADD COLUMN IF NOT EXISTS agent_type VARCHAR(50) DEFAULT 'interactive';
ALTER TABLE session_events ADD COLUMN IF NOT EXISTS parent_session VARCHAR(255);

-- Session lifecycle: explicit close tracking + synthesis result
-- closed_at is set per-session (on first batch row) by the close endpoint
ALTER TABLE session_events ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE session_events ADD COLUMN IF NOT EXISTS synthesis JSONB;

-- Index for multi-agent parent→child queries
CREATE INDEX IF NOT EXISTS idx_session_events_parent
    ON session_events (parent_session)
    WHERE parent_session IS NOT NULL;

-- Index for finding open sessions efficiently
CREATE INDEX IF NOT EXISTS idx_session_events_closed
    ON session_events (session_name, closed_at);
