-- Migration 036: Health alerting rules and history.
-- Phase 4 of Watchtower (v0.63.0): proactive notifications for operational issues.

CREATE TABLE IF NOT EXISTS alert_rules (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    condition_type  VARCHAR(64) NOT NULL,       -- 'metric_threshold', 'health_status'
    condition       JSONB NOT NULL,             -- type-specific params
    notification    JSONB,                      -- delivery config (e.g. {"webhook_id": 5})
    severity        VARCHAR(16) NOT NULL DEFAULT 'warning',  -- critical, warning, info
    is_active       BOOLEAN NOT NULL DEFAULT true,
    cooldown_minutes INTEGER NOT NULL DEFAULT 60,
    last_fired_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_active
    ON alert_rules (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_alert_rules_condition_type
    ON alert_rules (condition_type);

CREATE TABLE IF NOT EXISTS alert_history (
    id              BIGSERIAL PRIMARY KEY,
    rule_id         INTEGER NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
    severity        VARCHAR(16) NOT NULL,
    message         TEXT NOT NULL,
    context         JSONB,                      -- snapshot of evaluated data
    delivered       BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_history_rule
    ON alert_history (rule_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_history_created
    ON alert_history (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_history_severity
    ON alert_history (severity, created_at DESC);
