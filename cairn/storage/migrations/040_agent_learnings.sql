-- Agent persistent memory — compound learning across dispatches (ca-158)

CREATE TABLE IF NOT EXISTS agent_learnings (
    id              SERIAL PRIMARY KEY,
    agent_name      VARCHAR(255) NOT NULL,
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    content         TEXT NOT NULL,
    learning_type   VARCHAR(50) NOT NULL DEFAULT 'general',
    importance      REAL NOT NULL DEFAULT 0.6,
    work_item_display_id VARCHAR(50),
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_learnings_agent
    ON agent_learnings (agent_name, active, importance DESC);

CREATE INDEX IF NOT EXISTS idx_agent_learnings_project
    ON agent_learnings (project_id, active);
