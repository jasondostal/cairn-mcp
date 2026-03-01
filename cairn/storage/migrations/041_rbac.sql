-- Multi-User Identity & RBAC (ca-124)
-- Users, project membership, and ownership columns.
-- All new columns nullable — existing data stays valid, single-user mode never populates them.

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(255) UNIQUE NOT NULL,
    email         VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(50) NOT NULL DEFAULT 'user',  -- admin | user | agent
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_projects (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role       VARCHAR(50) NOT NULL DEFAULT 'member',  -- owner | member | viewer
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, project_id)
);

ALTER TABLE memories   ADD COLUMN IF NOT EXISTS owner_user_id INTEGER REFERENCES users(id);
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER REFERENCES users(id);
ALTER TABLE projects   ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER REFERENCES users(id);
