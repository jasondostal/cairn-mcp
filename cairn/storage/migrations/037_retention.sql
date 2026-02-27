-- Watchtower Phase 5: Data retention policies
-- Configurable TTLs per resource type, legal hold, scheduled cleanup.

CREATE TABLE IF NOT EXISTS retention_policies (
    id              SERIAL PRIMARY KEY,
    project_id      VARCHAR(128),                   -- NULL = global (all projects)
    resource_type   VARCHAR(64)  NOT NULL,           -- events, usage_events, metric_rollups, webhook_deliveries, alert_history, audit_log, event_dispatches
    ttl_days        INTEGER      NOT NULL,
    legal_hold      BOOLEAN      NOT NULL DEFAULT false,
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    last_run_at     TIMESTAMPTZ,
    last_deleted    INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, resource_type)
);

CREATE INDEX IF NOT EXISTS idx_retention_active ON retention_policies (is_active);
