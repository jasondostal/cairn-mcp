-- Multi-backend workspace sessions: rename opencode-specific column, add backend tracking.
-- Non-destructive: renames column (data preserved), defaults existing rows to 'opencode'.

ALTER TABLE workspace_sessions RENAME COLUMN opencode_session_id TO backend_session_id;

ALTER TABLE workspace_sessions ADD COLUMN IF NOT EXISTS backend VARCHAR(50) NOT NULL DEFAULT 'opencode';

ALTER TABLE workspace_sessions ADD COLUMN IF NOT EXISTS backend_metadata JSONB NOT NULL DEFAULT '{}';

-- Update indexes for the renamed column
DROP INDEX IF EXISTS idx_workspace_sessions_opencode_id;
CREATE INDEX IF NOT EXISTS idx_workspace_sessions_backend_id ON workspace_sessions(backend_session_id);
CREATE INDEX IF NOT EXISTS idx_workspace_sessions_backend ON workspace_sessions(backend);
