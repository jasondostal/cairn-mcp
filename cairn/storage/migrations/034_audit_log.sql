-- Migration 034: Immutable audit log for compliance tracking.
-- Phase 2 of Watchtower (v0.63.0): every mutation gets an append-only audit entry.

CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        VARCHAR(32),
    actor           VARCHAR(50),
    entry_point     VARCHAR(255),
    action          VARCHAR(50) NOT NULL,
    resource_type   VARCHAR(50) NOT NULL,
    resource_id     INTEGER,
    project_id      INTEGER,
    session_name    VARCHAR(255),
    before_state    JSONB,
    after_state     JSONB,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Partial indexes for filtered queries
CREATE INDEX IF NOT EXISTS idx_audit_log_trace_id
    ON audit_log (trace_id) WHERE trace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_log_action
    ON audit_log (action);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource
    ON audit_log (resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_project_id
    ON audit_log (project_id) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
    ON audit_log (created_at);
