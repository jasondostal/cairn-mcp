-- Migration 035: Webhook subscriptions and delivery tracking.
-- Phase 3 of Watchtower (v0.63.0): push event notifications to external HTTP endpoints.

CREATE TABLE IF NOT EXISTS webhooks (
    id              BIGSERIAL PRIMARY KEY,
    project_id      INTEGER REFERENCES projects(id),
    name            VARCHAR(255) NOT NULL,
    url             TEXT NOT NULL,
    secret          TEXT NOT NULL,                -- HMAC-SHA256 signing key
    event_types     TEXT[] NOT NULL DEFAULT '{}',  -- patterns: 'memory.created', 'work_item.*'
    is_active       BOOLEAN NOT NULL DEFAULT true,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhooks_project_id
    ON webhooks (project_id) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_webhooks_active
    ON webhooks (is_active) WHERE is_active = true;

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id              BIGSERIAL PRIMARY KEY,
    webhook_id      BIGINT NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event_id        BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts        INT NOT NULL DEFAULT 0,
    max_attempts    INT NOT NULL DEFAULT 5,
    request_body    JSONB,
    response_status INT,
    response_body   TEXT,
    last_error      TEXT,
    next_retry      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_pending
    ON webhook_deliveries (next_retry)
    WHERE status IN ('pending', 'failed');
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook_id
    ON webhook_deliveries (webhook_id);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_event_id
    ON webhook_deliveries (event_id);
