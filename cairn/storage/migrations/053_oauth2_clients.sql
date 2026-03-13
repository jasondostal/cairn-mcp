-- OAuth2 Authorization Server: Dynamic Client Registration + Refresh Tokens
-- Enables remote MCP clients (e.g. Claude.ai) to connect via OAuth2

CREATE TABLE IF NOT EXISTS oauth2_clients (
    client_id TEXT PRIMARY KEY,
    client_secret TEXT,
    client_id_issued_at INTEGER NOT NULL,
    client_secret_expires_at INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth2_refresh_tokens (
    token TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES oauth2_clients(client_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scopes TEXT[] NOT NULL DEFAULT '{}',
    expires_at INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oauth2_refresh_tokens_user ON oauth2_refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_oauth2_refresh_tokens_client ON oauth2_refresh_tokens(client_id);
