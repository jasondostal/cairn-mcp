-- Migration 039: Event subscriptions and in-app notifications.
-- Part of ca-146: pattern-based subscribe/notify for human/agent collaboration.
-- Generalizes the webhook pattern to support in-app, push, and SSE channels.

CREATE TABLE IF NOT EXISTS event_subscriptions (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    patterns        TEXT[] NOT NULL DEFAULT '{}',       -- event type patterns: 'work_item.completed', 'work_item.*', 'deliverable.*:project=cairn'
    channel         VARCHAR(50) NOT NULL DEFAULT 'in_app', -- in_app, webhook, push, sse
    channel_config  JSONB NOT NULL DEFAULT '{}',        -- channel-specific config (push endpoint, webhook url, etc.)
    project_id      INTEGER REFERENCES projects(id),    -- scope to project (NULL = all projects)
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_subscriptions_active
    ON event_subscriptions (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_event_subscriptions_channel
    ON event_subscriptions (channel);
CREATE INDEX IF NOT EXISTS idx_event_subscriptions_project
    ON event_subscriptions (project_id) WHERE project_id IS NOT NULL;

-- In-app notifications — the "bell icon" inbox
CREATE TABLE IF NOT EXISTS notifications (
    id              BIGSERIAL PRIMARY KEY,
    subscription_id BIGINT REFERENCES event_subscriptions(id) ON DELETE SET NULL,
    event_id        BIGINT REFERENCES events(id) ON DELETE CASCADE,
    title           VARCHAR(500) NOT NULL,
    body            TEXT,
    severity        VARCHAR(20) NOT NULL DEFAULT 'info',  -- info, warning, error, success
    is_read         BOOLEAN NOT NULL DEFAULT false,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    read_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notifications_unread
    ON notifications (created_at DESC) WHERE is_read = false;
CREATE INDEX IF NOT EXISTS idx_notifications_subscription
    ON notifications (subscription_id);
CREATE INDEX IF NOT EXISTS idx_notifications_created
    ON notifications (created_at DESC);
