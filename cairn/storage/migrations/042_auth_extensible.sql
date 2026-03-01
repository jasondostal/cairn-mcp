-- Extensible auth: OIDC users + Personal Access Tokens (ca-162)

-- OIDC users don't have local passwords
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

-- Track how the user was created (local password vs OIDC)
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(50) NOT NULL DEFAULT 'local';

-- External IdP identity (e.g. OIDC sub claim)
ALTER TABLE users ADD COLUMN IF NOT EXISTS external_id VARCHAR(255);

-- One external_id per auth_provider
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider_external
    ON users (auth_provider, external_id)
    WHERE external_id IS NOT NULL;

-- Personal Access Tokens for machine clients (Claude Code, CI, scripts)
CREATE TABLE IF NOT EXISTS api_tokens (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          VARCHAR(255) NOT NULL,
    token_hash    VARCHAR(64) NOT NULL UNIQUE,    -- SHA-256 hex digest
    token_prefix  VARCHAR(12) NOT NULL,           -- first 12 chars for display
    scopes        VARCHAR(255) NOT NULL DEFAULT '*',
    expires_at    TIMESTAMPTZ,
    last_used_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id ON api_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens (token_hash) WHERE is_active = TRUE;
