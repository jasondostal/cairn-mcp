-- Migration 015: Messages — inter-agent communication layer.
-- Lightweight message system for agents to leave notes for the user (and each other).

CREATE TABLE IF NOT EXISTS messages (
    id          SERIAL PRIMARY KEY,
    project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    sender      VARCHAR(100) NOT NULL,
    content     TEXT NOT NULL,
    priority    VARCHAR(20) DEFAULT 'normal',
    is_read     BOOLEAN DEFAULT false,
    archived    BOOLEAN DEFAULT false,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_unread
    ON messages (is_read, created_at DESC) WHERE NOT archived;
CREATE INDEX IF NOT EXISTS idx_messages_project
    ON messages (project_id, created_at DESC);
