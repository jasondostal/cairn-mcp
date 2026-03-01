-- Migration 043: Groups for user management (ca-171)
-- Adds groups with membership and project access tables.

CREATE TABLE IF NOT EXISTS groups (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) UNIQUE NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source      VARCHAR(50) NOT NULL DEFAULT 'manual',  -- manual | oidc
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id  INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    added_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS group_projects (
    group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role       VARCHAR(50) NOT NULL DEFAULT 'member',
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (group_id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members (user_id);
CREATE INDEX IF NOT EXISTS idx_group_projects_project ON group_projects (project_id);
