-- Workspace sessions: tracks OpenCode sessions linked to Cairn projects
CREATE TABLE IF NOT EXISTS workspace_sessions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    opencode_session_id VARCHAR(255) NOT NULL,
    agent VARCHAR(255) NOT NULL DEFAULT 'cairn-build',
    title VARCHAR(512),
    task TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspace_sessions_project
    ON workspace_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_workspace_sessions_opencode_id
    ON workspace_sessions(opencode_session_id);
CREATE INDEX IF NOT EXISTS idx_workspace_sessions_created
    ON workspace_sessions(created_at DESC);
