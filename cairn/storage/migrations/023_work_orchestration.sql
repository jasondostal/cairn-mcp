-- v0.48.0: Work Orchestration — gates, risk tiers, agent state, activity log
-- Additive only: all new columns are nullable or have defaults.

-- Gate primitives (human-in-the-loop)
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS gate_type VARCHAR(20);
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS gate_data JSONB DEFAULT '{}';
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS gate_resolved_at TIMESTAMPTZ;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS gate_response JSONB;

-- Cascading constraints
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS constraints JSONB DEFAULT '{}';

-- Risk tier (0-3: patrol, caution, action, critical)
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS risk_tier INTEGER DEFAULT 0;

-- Agent state + heartbeat
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS agent_state VARCHAR(20);
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ;

-- Activity log
CREATE TABLE IF NOT EXISTS work_item_activity (
    id SERIAL PRIMARY KEY,
    work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    actor VARCHAR(255),
    activity_type VARCHAR(30) NOT NULL,
    content TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_work_item_activity_item
    ON work_item_activity (work_item_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_work_item_activity_type
    ON work_item_activity (activity_type);

-- Partial indexes on new work_items columns
CREATE INDEX IF NOT EXISTS idx_work_items_gate
    ON work_items (gate_type) WHERE gate_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_work_items_risk
    ON work_items (risk_tier) WHERE risk_tier > 0;
CREATE INDEX IF NOT EXISTS idx_work_items_agent_state
    ON work_items (agent_state) WHERE agent_state IS NOT NULL;
