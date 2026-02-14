-- SSH host management for web terminal (native + ttyd backends)
CREATE TABLE IF NOT EXISTS ssh_hosts (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    hostname        VARCHAR(255) NOT NULL,
    port            INTEGER DEFAULT 22,
    username        VARCHAR(100),
    auth_method     VARCHAR(20) DEFAULT 'password',
    encrypted_creds TEXT,
    ttyd_url        TEXT,
    description     TEXT,
    is_active       BOOLEAN DEFAULT true,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ssh_hosts_active ON ssh_hosts (is_active, name);
